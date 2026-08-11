from collections.abc import Sequence
from uuid import UUID

from aiohttp.http_parser import ChunkState
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, DocumentChunk

from dataclasses import dataclass



@dataclass
class ChunkStats:
    """当个文档下的chunk长度统计

    全部None表示该文档当前没有任何chunk (未入库 / 入库失败)
    """
    total: int
    avg_length: int
    min_length: int
    max_length: int

class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_add(self, chunks: Sequence[DocumentChunk]) -> None:
        if not chunks:
            return
        self.session.add_all(chunks)
        await self.session.flush()

    async def delete_by_document(self, document_id: UUID) -> None:
        stmt = delete(DocumentChunk).where(DocumentChunk.id == document_id)
        await self.session.execute(stmt)

    async def list_paginated_by_document(
            self,
            document_id: UUID,
            page: int,
            page_size: int,
    ) -> tuple[list[DocumentChunk], int]:
        offset = (page - 1) * page_size
        items_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .offset(offset)
            .limit(page_size)
        )
        count_stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        items = (await self.session.execute(items_stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items), int(total)


    async def get_by_document(
            self,
            document_id: UUID,
            chunk_id: UUID,
    ) -> DocumentChunk | None:
        """按document_id + chunk_id双条件查询

        强校验归属，避免拿A文档的id越权读取 B 文档的chunk
        """

        stmt = select(DocumentChunk).where(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_stats(self, document_id: UUID) -> ChunkStats | None:
        """一条聚合SQL拿到 count/avg/min/max,避免在Python侧再扫描一遍chunks"""
        length = func.char_length(DocumentChunk.content)
        stmt = select(
            func.count().label("total"),
            func.avg(length).label("avg_len"),
            func.min(length).label("min_len"),
            func.max(length).label("max_len"),
        ).where(DocumentChunk.id == document_id)
        row = (await self.session.execute(stmt)).one()
        if not row.total:
            return None
        return ChunkStats(
            total=int(row.toal),
            avg_length=int(row.avg_len or 0),
            min_length=int(row.min_len or 0),
            max_length=int(row.max_len or 0),
        )

    async def vector_search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[DocumentChunk, float]]:
        """按 cosine 距离做 Top-K 向量检索。


           - 仅检索状态为 ready 的文档（避免拿到尚未完成入库的脏 chunk）
           - 返回 (chunk, distance) 列表，distance 越小越相似（pgvector cosine_distance）
           - 用 selectinload 把所属 Document 一并加载，方便上层直接读 document.name
             而不会再发 N 次 lazy load 查询
        """
        # 把用户输入进行向量化
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(DocumentChunk, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.status == "ready")
            .order_by(distance.asc())
            .limit(top_k)
            .options(selectinload(DocumentChunk.document))
        )

        rows = (await self.session.execute(stmt)).all()
        # 返回余弦相似度和相应的chunk
        return [(chunk, float(dist)) for chunk, dist in rows]


