import asyncio
from uuid import UUID

# 支持langchian的文档类型
from langchain_core.documents import Document as LangChainDocument

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


async def _run_reindex(document_id: UUID, task_id: UUID) -> None:
    """增量重建：按 chunk_hash 对齐，仅对变化部分重新 embedding。

    与 _run_ingest 的区别：
    - 命中的 chunk 不重新计算 embedding，仅更新 chunk_index / metadata
    - 新增 chunk 才走 embedding，progress_total 也只统计新增数量
    - 全删全插作为 hash 冲突场景的兜底
    """
    logger.info("reindex start: document_id=%s, task_id=%s", document_id, task_id)
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

            # 设置状态： 解析
            await _set_status(document_id, DocumentStatus.PARSING)
            content = await get_file_service().download(object_key)
            parsed = await parser.parse(filename, content)
            # 设置状态： 索引
            await _set_status(document_id, DocumentStatus.INDEXING)
            new_chunks = splitter.split(parsed)
            if not new_chunks:
                raise ValueError("切分后没有任何chunk, 请检查文档内容")

            async with AsyncSessionLocal() as session:
                old_chunks = await DocumentChunkRepository(session).list_all_by_document(
                    document_id,
                )


            if _has_duplicate_hash(new_chunks):                      # F：预检，判断新的chunks和数据库中的chunks
                # 同文档内 chunk_hash 重复（多见于极短文档或重复段落），
                # 增量对齐逻辑会歧义；退化为「全删全插」是最稳的兜底
                logger.warning(
                    "reindex fallback to full rebuild due to duplicate chunk: %s",
                    document_id,
                )
                await _run_full_rebuild(document_id, task_id, new_chunks)   # F：
            else:
                await _run_incremental(document_id, task_id, old_chunks, new_chunks) # F:

            # 内容已经成功重建： 版本号 + 1
            async with AsyncSessionLocal() as session:
                doc_repo = DocumentRepository(session)
                doc = await doc_repo.get_by_id(document_id)
                if doc is not None:
                    doc.version += 1
                await session.commit()

            await _set_status(document_id, DocumentStatus.READY, error_message=None)
            await _mark_task_success(task_id)
    except Exception as exc:
        logger.exception("reindex failed: document_id=%s", document_id)
        message = str(exc).strip() or exc.__class__.__name__
        await _set_status(document_id, DocumentStatus.FAILED, error_message=message[:500])
        await _mark_task_failed(task_id, message)


# 预检操作
# 用chunk_hash作为新旧 chunk 的唯一标识，把新切分出来的 chunks 和数据库里已有的 chunks 逐条配对
# hash 相同的视为「内容没变」，hash 在旧集合里找不到的是「新增」，旧集合里有但新集合里没有的是「待删除」。
def _has_duplicate_hash(chunks: list[LangChainDocument]) -> bool:
    seen: set[str] = set()
    for c in chunks:
        h = c.metadata["chunk_hash"]
        if h in seen:
            return True
        seen.add(h)
    return False


async def _run_incremental(
        document_id: UUID,
        task_id: UUID,
        old_chunks: list[DocumentChunk],
        new_chunks: list[LangChainDocument],
) -> None:
    """按 chunk_hash 对齐增删改。
    分类规则：
    - old 中存在但 new 已经没有的 hash → DELETE
    - new 中已存在的 hash → 只更新 chunk_index / metadata，不重新 embedding
    - new 中不存在于 old 的 hash → INSERT，需要 embedding
    """
    old_by_hash = {c.chunk_hash: c for c in old_chunks}
    new_hashes = {c.metadata["chunk_hash"] for c in new_chunks}

    # 确认要删除的文档
    to_delete_ids: list[UUID] = [
        c.id for c in old_chunks if c.chunk_hash not in new_hashes
    ]
    # 确认要增加的文档
    to_insert: list[LangChainDocument] = []
    # 确认要更新的文档
    to_update: list[tuple[DocumentChunk, LangChainDocument]] = []
    # 对齐操作
    for nc in new_chunks:
        h = nc.metadata["chunk_hash"]
        existing = old_by_hash.get(h)
        if existing is None:
            to_insert.append(nc)
        else:
            to_update.append((existing, nc))


    await _set_task_total(task_id, len(to_insert))
    new_embedding = await _embed_with_progress(
        [c.page_content for c in to_insert], task_id
    )

    # 数据库操作
    async with AsyncSessionLocal() as session:
        chunk_repo = DocumentChunkRepository(session)
        # 删除旧chunk
        await chunk_repo.delete_by_ids(to_delete_ids)

        # 更新命中 chunk 的位置 / 段落元数据：内容（即 hash）未变所以不动 embedding
        for old, nc in to_update:
            old.chunk_index = nc.metadata["chunk_index"]
            old.page_no = nc.metadata.get("page_no")
            old.section_path = nc.metadata.get("section_path")
            old.extra_metadata = nc.metadata
        # 更新
        await chunk_repo.bulk_add(
            [
                _make_chunk(document_id, c, vec)
                for c, vec in zip(to_insert, new_embedding, strict=True)
            ]
        )
        await session.commit()

async def _run_full_rebuild(
        document_id: UUID,
        task_id: UUID,
        new_chunks: list[LangChainDocument],
) -> None:
    """hash 冲突场景的兜底：清空旧 chunks，全量 embedding 后写入。"""
    await _set_task_total(task_id, len(new_chunks))
    embeddings = await _embed_with_progress(
        [c.page_content for c in new_chunks ], task_id
    )

    # 数据库操作
    async with AsyncSessionLocal() as session:
        chunk_repo = DocumentChunkRepository(session)
        await chunk_repo.delete_by_document(document_id)
        await chunk_repo.bulk_add(
            [
                _make_chunk(document_id, c, vec)
                for c, vec in zip(new_chunks, embeddings, strict=True)
            ]
        )
        await session.commit()

# 设置任务总量
async def _set_task_total(task_id: UUID, total: int) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.set_progress_total(task_id, total)
        await session.commit()

async def _increment_task_progress(task_id: UUID, delta: int) -> None:
    async with AsyncSessionLocal() as session:
        repo = IngestionTaskRepository(session)
        await repo.increment_progress(task_id, delta)
        await session.commit()








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
