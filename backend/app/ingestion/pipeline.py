from uuid import UUID

from app.core.logging import get_logger
from app.db.models import DocumentChunk, DocumentStatus
from app.db.repositories.chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.session import AsyncSessionLocal
from app.ingestion import embedder, parser, splitter
from app.storage.file_service import get_file_service


logger = get_logger(__name__)

# 用于改变文档当前状态
async def _set_status(
        document_id: UUID,
        status: DocumentStatus,
        *,
        error_message: str | None = None
) -> None:
    """状态变更独立事务：避免长事务、保证前端轮询能立即看到中间态。"""
    async with AsyncSessionLocal() as session:
        repo = DocumentRepository(session)
        await repo.update_status(document_id, status, error_message=error_message)
        await session.commit()


async def ingest_document(document_id: UUID) -> None:
    """执行完整入库流程"""
    logger.info(f"ingest start: document_id=%s", document_id)

    try:
        async with AsyncSessionLocal() as session:
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(document_id)
            if document is None:
                logger.warning(f"document not found, skip ingest: %s", document_id)
                return
            object_key = document.cos_object_key
            filename = document.name

        # 解析
        await _set_status(document_id, DocumentStatus.PARSING)
        content = await get_file_service().download(object_key)
        documents = await parser.parse(filename, content)

        # 切分
        await _set_status(document_id, DocumentStatus.INDEXING)
        chunks = splitter.split(documents)
        if not chunks:
            raise ValueError("切分后没有任何 chunk，请检查文档内容")

        # 定义向量模型
        embeddings = await embedder.get_embeddings().aembed_documents(
            [c.page_content for c in chunks]
        )

        # 把切分后的块存入数据库
        async with AsyncSessionLocal() as session:
            chunk_repo = DocumentChunkRepository(session)
            chunk_repo.session.add_all(
                [
                    DocumentChunk(
                        document_id=document_id,
                        content=c.page_content,
                        embedding=vec,
                        page_no=c.metadata.get("page_no"),
                        section_path=c.metadata.get("section_path"),
                        chunk_index=c.metadata["chunk_index"],
                        chunk_hash=c.metadata["chunk_hash"],
                        extra_metadata=c.metadata,
                    )
                    for c, vec in zip(chunks, embeddings, strict=True)
                ]
            )
            await session.commit()
        # 设置已经完成切分
        await _set_status(document_id, DocumentStatus.READY, error_message=None)
        logger.info(f"ingest done: document_id=%s, chunks=%d", document_id, len(chunks))

    except Exception as exc:
        logger.exception("ingest failed: document_id=%s", document_id)
        # 注意：str(exc).split() 返回的是 list[str]，
        # 传给 error_message（PG Text 列）会被 asyncpg 拒收。
        # 只截断字符串，保留可读性。
        message = str(exc) or exc.__class__.__name__
        try:
            await _set_status(
                document_id,
                DocumentStatus.FAILED,
                error_message=message[:500],
            )
        except Exception:
            # 状态回写失败也不能再次逃逸，否则文档会永久卡在
            # PARSING / INDEXING，前端轮询看不到终态。
            logger.exception(
                "failed to mark document as FAILED: id=%s", document_id
            )
