from langchain_core.embeddings import Embeddings
from langchain_openai.embeddings import OpenAIEmbeddings

from app.core.config import settings
from app.core.exceptions import ConfigurationError

_embeddings: Embeddings | None = None

def get_embeddings() -> Embeddings:
    """设置向量化模型"""
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    if not settings.embedding_base_url:
        raise ConfigurationError("相关Key未进行配置， 请在.env中进行配置")

    _embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dim,
        chunk_size=settings.embedding_batch_size,
        check_embedding_ctx_length=False,
    )
    return _embeddings