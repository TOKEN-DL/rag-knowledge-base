from typing import TypedDict
from uuid import UUID
from typing import Literal, TypedDict

from app.db.models import Message
from app.retrieval.vector_retriever import RetrievedChunk

QueryRoute = Literal["original", "rewrite", "hyde", "multi_query"]

class RAGState(TypedDict, total=False):
    # 输入
    conversation_id: UUID
    question: str

    # load_context 产出
    chat_history: list[Message]

    # normalize_query 产出（本章 = question）
    query: str

    # router_query产出
    route: QueryRoute
    rewritten_query: str | None
    hyde_answer: str | None
    multi_queries: str | None

    # retrieve产出
    retrieved_chunks: list[RetrievedChunk]
    # 是否触发拒答
    refused: bool

    # Agentic RAG 循环：plan_retrieval / observe_context 产出
    # agent_steps 每一项形如 {round, action, reason, route, query, retrieved_count, top_score, sufficient}
    # 由 plan_retrieval 追加"决策"字段、observe_context 回填"观察"字段，避免分两条记录
    agent_steps: list[dict]
    retrieval_round: int

    # observe_context 判定本轮候选是否足够；True 时图走出循环进入 rerank
    context_sufficient: bool

    # rerank 后基于 Top1 score 的拒答闸门
    # False 时图走向 refuse 节点；True 时图走向 END
    context_is_enough: bool

    # generate 产出
    answer: str

    # chat_service落库后回写
    user_message_id: UUID
    assistant_message_id: UUID

    # LangSmith trace_id：未启用观测 / 取不到 run tree 时为 None
    # 仅由 service 层 stream_answer 进入 @traceable 上下文后写入，节点不感知
    trace_id: str | None

