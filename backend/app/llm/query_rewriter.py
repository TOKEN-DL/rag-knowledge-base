from dataclasses import dataclass
from typing import get_args

from app.core.logging import get_logger
from app.llm.models import get_chat_model
from app.llm.prompts import (
    build_hyde_messages,
    build_multi_query_messages,
    build_route_messages,
    build_rewrite_messages
)
from app.workflows.rag_state import QueryRoute

logger = get_logger(__name__)

_VALID_ROUTES: tuple[str, ...] =get_args(QueryRoute)

@dataclass
class QueryRouterResult:
    """Query 优化的统一返回结构。
        - route：最终采用的策略
        - query：要喂给向量检索的查询文本（rewrite/hyde 路径下是改写文本，其余是原问题）
        - 余下三个字段按 route 选择性填充，便于前端调试展示和落库
    """
    route: QueryRoute
    query: str
    rewritten_query: str | None = None
    hyde_answer: str | None = None
    multi_queries: list[str] | None = None

class QueryRewriter:
    """4 步 Query 优化的协同入口。所有 LLM 调用都走单例 ChatOpenAI。"""

    async def decide_route(self, question: str) -> QueryRoute:
        messages = build_route_messages(question)
        response = await get_chat_model().ainvoke(messages)
        raw = _extract_text(response.content.strip().lower())

        token = raw.strip("\"'`.。 ")
        if token in _VALID_ROUTES:
            return token
        logger.warning("query route模型返回非法值，降级 original： raw=%r", raw)
        return "original"

    async def rewrite(self, question: str) -> str:
        messages = build_rewrite_messages(question)
        response = await get_chat_model().ainvoke(messages)
        return _extract_text(response.content).strip()

    async def hyde(self, question: str) -> str:
        messages = build_hyde_messages(question)
        response = await get_chat_model().ainvoke(messages)
        return _extract_text(response.content).strip()

    async def multi_query(self, question: str, n: int) -> list[str]:
        messages = build_multi_query_messages(question)
        response = await get_chat_model().ainvoke(messages)
        text = _extract_text(response.content)
        queries = [line.strip(" -•*0123456789.、") for line in text.splitlines()]
        return [q for q in queries if q][:n]


    async def optimize(self, question: str, multi_query_count: int) -> QueryRouterResult:
        """按 route 分发并填充结果。任何一步失败都安全降级到 original。"""
        try:
            route = await self.decide_route(question)
            if route == "rewrite":
                rewritten = await self.rewrite(question)
                if not rewritten:
                    return QueryRouterResult(route="original", query=question)
                return QueryRouterResult(
                    route="rewrite", query=rewritten, rewritten_query=rewritten
                )
            if route == "hyde":
                hyde_answer = await self.hyde(question)
                if not hyde_answer:
                    return QueryRouterResult(route="hyde", query=question)
                return QueryRouterResult(route="hyde", query=hyde_answer, hyde_answer=hyde_answer)
            if route == "multi_query":
                queries = await self.multi_query(question, multi_query_count)
                if len(queries) < 2:
                    return QueryRouterResult(route="multi_query", query=question)
                return QueryRouterResult(route="multi_query", multi_queries=queries)
            return QueryRouterResult(route="original", query=question)
        except Exception:
            logger.exception("query optimize失败，降级到original:question=%r", question)
            return QueryRouterResult(route="original", query=question)

def _extract_text(content: str | list[str | dict]) -> str:
    """兼容 langchain ChatModel 的 content 联合类型"""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


_rewriter: QueryRewriter | None = None

def get_query_rewriter() -> QueryRewriter:
    """单例调用rewriter"""
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter()
    return _rewriter