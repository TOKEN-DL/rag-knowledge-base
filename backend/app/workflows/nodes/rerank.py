from app.core.config import settings
from app.llm.reranker import get_reranker
from app.workflows.rag_state import RAGState


async def rerank(state: RAGState) -> RAGState:
    chunks = state.get("retrieved_chunks", [])
    if not settings.rerank_enabled or len(chunks) <= 1:
        return {}
    # 根据query和粗筛chunk，进行一轮精筛
    reranked = await get_reranker().rerank(state["query"], chunks)
    return {"retrieved_chunks":reranked[:settings.retrieval_top_k]}