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

    # generate 产出
    answer: str

    # chat_service落库后回写
    user_message_id: UUID
    assistant_message_id: UUID

