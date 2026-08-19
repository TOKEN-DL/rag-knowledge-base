from app.llm.query_rewriter import get_query_rewriter

from app.workflows.rag_state import RAGState

async def normalize_query(state: RAGState) -> RAGState:
    history =state.get("chat_history") or []
    if not history:
        return {"query": state["question"]}

    # 根据上下文进行重写
    rewritten = await get_query_rewriter().contextualize(
        question=state["question"], history=history
    )
    return {"query": rewritten}

