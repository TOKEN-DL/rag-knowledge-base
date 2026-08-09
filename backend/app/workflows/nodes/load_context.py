
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.repositories.conversation_repo import ConversationRepository
from app.workflows.rag_state import RAGState

async def load_context(state: RAGState, session: AsyncSession) -> RAGState:
    """加载上下文， 从state获取上下文数据， 调用session操作数据库，最后返回数据回state，
    下一个节点可以获取state里的数据从而拿到该节点的输出
    """
    repo = ConversationRepository(session)
    # 多轮窗口按消息条数截取
    history = await repo.recent_messages(
        state["conversation_id"], limit=settings.chat_history_window * 2
    )
    return {"chat_history": history}
