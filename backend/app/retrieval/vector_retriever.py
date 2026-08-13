from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.db.repositories import chunk_repo
from app.db.repositories.chunk_repo import DocumentChunkRepository
from app.ingestion.embedder import get_embeddings

@dataclass(frozen=True)
class RetrievedChunk:
    """检索结果中单个chunk的展示视图

    score是cosine similarity （已统一成“越大越相似”）
    便于上层做阈值判断
    """

    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    page_no: int | None
    section_path: str | None
    score: float

    # 混合检索支持
    sources: tuple[str, ...] = field(default_factory=tuple)
    vector_rank: int | None = None
    vector_score: float | None = None  # 原始 cosine similarity（向量路命中时填充）
    keyword_rank: int | None = None
    keyword_score: float | None = None # 原始 ts_rank（关键词路命中时填充）
    rrf_score: float | None = None


class VectorRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.chunk_repo = DocumentChunkRepository(session)

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        embedding = await get_embeddings().aembed_query(query)
        rows = await self.chunk_repo.vector_search(embedding, top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document.name,
                content=chunk.content,
                page_no=chunk.page_no,
                section_path=chunk.section_path,
                # pgvector cosine_distance ∈ [0, 2]；标准化为 similarity
                # 同方向归一化向量下，distance ∈ [0, 1]，similarity ∈ [0, 1]
                score=1.0 - distance,
                sources=("vector",),
                vector_rank=rank,
                vector_score=1.0 - distance

            )
            for rank, (chunk ,distance) in enumerate(rows, start=1)
        ]

