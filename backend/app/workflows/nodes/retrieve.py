"""retrieve：执行向量 Top-K 检索，并判断是否触发拒答。
multi_query 路径下需要多路召回 + 去重；其他路径走单路。
"""


from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.llm.prompts import REFUSAL_ANSWER
from app.retrieval.vector_retriever import VectorRetriever, RetrievedChunk
from app.retrieval.hybrid_retriever import HybridRetriever
from app.workflows.rag_state import RAGState

async def retrieve(state: RAGState) -> RAGState:
    retriever = HybridRetriever()   # 改造成混合检索
    recall_top_k = settings.retrieval_recall_top_k
    final_top_k = settings.retrieval_top_k

    if state.get("route") == "multi_query" and state.get("multi_queries"):
        # 各子查询独立召回，再合并
        bundles: list[list[RetrievedChunk]] = []
        for sub_query in state["multi_queries"] or []:
            bundles.append(
                await retriever.search(
                    sub_query,
                    recall_top_k=recall_top_k,
                    final_top_k=final_top_k))
        chunks = _merge_chunks(bundles, top_k=final_top_k)
    else:
        chunks = await retriever.search(
            state["query"],
            recall_top_k=recall_top_k,
            final_top_k=final_top_k)


    # 检索为空 / 最高相似度过低 → 直接拒答；不再调 LLM
    refused = _should_refuse(chunks)   # 这里用辅助函数进行判断
    update: RAGState = {
        "retrieved_chunks": chunks,
        "refused": refused,
    }
    if refused:
        update["answer"] = REFUSAL_ANSWER
    return update

def _should_refuse(chunks: list[RetrievedChunk]) -> bool:
    """混合检索后的拒答判定，仅看 Top1 的语义相关度。"""
    if not chunks:
        return True
    top = chunks[0]
    if top.vector_score is None:
        return True # Top1 仅命中关键词路，缺乏语义佐证
    return top.vector_score < settings.retrieval_min_score

def _merge_chunks(
        bundles: list[list[RetrievedChunk]], top_k: int
) -> list[RetrievedChunk]:
    """多路召回结果去重 + 取 Top-K。
        同一个 chunk 可能在多条子查询中都命中；这里保留最高 score，
        再整体按 score 降序取前 top_k。
    """
    best: dict[str, RetrievedChunk] = {}
    for bundle in bundles:
        for chunk in bundle:
            key = str(chunk.chunk_id)
            prev = best.get(key)
            if prev is None or (chunk.rrf_score or 0.0) > (prev.rrf_score or 0.0):
                best[key] = chunk
    ranked = sorted(best.values(), key=lambda c: c.rrf_score, reverse=True)
    return ranked[:top_k]



