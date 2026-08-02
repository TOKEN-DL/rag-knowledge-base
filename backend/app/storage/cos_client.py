"""腾讯云 COS 客户端封装"""

import asyncio

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

class CosClient:

    def __init__(self) -> None:
        if not settings.cos_configured:
            raise ConfigurationError("腾讯云 COS 未配置， 请在 .env中填写 COS_* 变量值")

        config = CosConfig(
            Region=settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key,
        )
        self._client = CosS3Client(config)
        self._bucket = settings.cos_bucket

    async def ping(self) -> bool:
        """通过 head_bucket 验证凭据与桶可达性"""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
            return True
        except (CosClientError, CosServiceError) as exc:
            logger.warning("COS ping failed : %s", exc)
        return False

_cos_client: CosClient | None = None

def get_cos_client() -> CosClient:
    """惰性构造：未配置时直接抛ConfigurationError, 由全局错误处理转503"""
    global _cos_client
    if _cos_client is None:
        _cos_client = CosClient()
    return _cos_client

