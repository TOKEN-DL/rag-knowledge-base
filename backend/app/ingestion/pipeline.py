import asyncio
from uuid import UUID

from instructor.cli.batch import results

from app.core.logging import get_logger
from app.db.models import DocumentChunk, DocumentStatus
from app.db.repositories.chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.ingestion_task_repo import IngestionTaskRepository
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

# 任务状态管理

async def _mark_task(task_id: UUID, *, running: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        if running:
            await repo.mark_running(task_id)
        await session.commit()

async def _mark_task_failed(task_id: UUID, error_message: str) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.mark_failed(task_id, error_message)
        await session.commit()

async def _mark_task_success(task_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.mark_success(task_id)
        await session.commit()

# 每批结束后立即把progress_done 写库，前端轮询每隔 3 秒就能看到进度。

async def _embed_with_progress(
        texts: list[str], task_id: UUID,
) -> list[list[float]]:
    """按 EMBEDDING_BATCH_SIZE 分批 embedding，逐批写入任务进度。

    LangChain `OpenAIEmbeddings.aembed_documents` 内部也会分批，但回调粒度藏在
    SDK 里；这里手动分批是为了让 `progress_done` 跟着每个批次走，前端轮询有连续反馈。
    """
    from app.core.config import settings

    if not texts:
        return []
    embeddings_client = embedder.get_embeddings()
    batch_size = max(1, settings.embedding_batch_size)
    results: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        vectors = await embeddings_client.aembed_documents(batch)
        results.extend(vectors)
        await _increment_task_progress(task_id, len(batch))  #F
    return results


async def _run_ingest(document_id: UUID, task_id: UUID) -> None:
    """首次入库：全量解析 → 切分 → embedding → 写库。"""
    logger.info("ingest start: document_id=%s, task_id=%s", document_id, task_id)
    await _mark_task(task_id, running=True)

    try:
        async with AsyncSessionLocal() as session:
            document = await DocumentRepository(session).get_by_id(document_id)
            if document is None:
                logger.warning("document not found, skip ingest: %s", document_id)
                await _mark_task_failed(task_id, "文档不存在")
                return
            object_key = document.cos_object_key
            filename = document.name

        # 解析文件
        await _set_status(document_id, DocumentStatus.PARSING)
        content = await get_file_service().download(object_key)
        parsed = await parser.parse(filename, content)
        # 索引
        await _set_status(document_id, DocumentStatus.INDEXING)
        chunks = splitter.split(parsed)
        if not chunks:
            raise ValueError("切分后没有任何chunk, 请检查文档内容")

        # 设置任务总数
        await _set_task_total(task_id, len(chunks))   #F

        embeddings = await _embed_with_progress(
            [c.page_content for c in chunks], task_id
        )

        async with AsyncSessionLocal() as session:
            chunk_repo = DocumentChunkRepository(session)
            await chunk_repo.bulk_add(
                [_make_chunk(document_id, c , vec) for c, vec in zip(chunks, embeddings, strict=True)], # F
            )
            await session.commit()

        await _set_status(document_id, DocumentStatus.READY, error_message=None)
        await _mark_task_success(task_id)
        logger.info("ingest done: document_id=%s, task_id=%s", document_id, task_id)

    except Exception as exc:
        logger.exception("ingest failed: document_id=%s", document_id)
        message = str(exc).strip() or exc.__class__.__name__
        await _set_status(document_id, DocumentStatus.FAILED, error_message=message[:500])
        await _mark_task_failed(task_id, message)


def _make_chunk(
        document_id: UUID, chunk: LangChainDocument, embedding: list[float]
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        content=chunk.page_content,
        embedding=embedding,
        page_no=chunk.metadata.get("page_no"),
        section_path=chunk.metadata.get("section_path"),
        chunk_index=chunk.metadata["chunk_index"],
        chunk_hash=chunk.metadata["chunk_hash"],
        extra_metadata=chunk.metadata,
    )


def run_ingest_sync(document_id: UUID, task_id: UUID) -> None:
    asyncio.run(_run_ingest(document_id, task_id))


def run_reindex_sync(document_id: UUID, task_id: UUID) -> None:
    asyncio.run(_run_reindex(document_id, task_id))










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
