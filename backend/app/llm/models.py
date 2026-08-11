from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import  ChatOpenAI

from app.core.config import settings
from app.core.exceptions import ConfigurationError

_chat_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    """返回流式ChatOpenAI实例

    单例缓存： 模型客户端持有httpx连接池，反复创建会有浪费
    :return:
    """
    global _chat_model
    if _chat_model is not None:
        return _chat_model

    if not settings.chat_api_key:
        return ConfigurationError("chat api key 还未设置")

    _chat_model = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.chat_api_key,
        base_url=settings.chat_base_url,
        temperature=0,
        streaming=True
    )
    return _chat_model

