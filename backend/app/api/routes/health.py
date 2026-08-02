"""健康检查接口： 验证后端、数据库、COS连通性"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.core.logging import get_logger
from app.storage.cos_client import get_cos_client


logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

HealthStatusValue = Literal["ok", "error", "not_configured"]

class HealthStatus(BaseModel):
    status: HealthStatusValue
    detail: str | None = None

@router.get("", response_model=HealthStatus, operation_id="healthApp")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


# 测试数据库连接情况
@router.get("/db", response_model=HealthStatus, operation_id="healthDb")
async def health_db(session: DbSession) -> HealthStatus :
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        return HealthStatus(status="ok")
    except Exception as exc:
        logger.exception("db health check failed")
        return HealthStatus(status="error", detail=str(exc))


# 测试cos连接情况
@router.get("/cos", response_model=HealthStatus, operation_id="healthCos")
async def health_cos() -> HealthStatus:
    if not settings.cos_configured:
        return HealthStatus(status="not_configured", detail="COS凭据未在.env中配置")
    try:
        ok = await get_cos_client().ping()
    except Exception as exc:
        logger.exception("cos health check failed")
        return HealthStatus(status="error", detail=str(exc))
    return HealthStatus(status="ok") if ok else HealthStatus(status="error", detail="head_bucket 失败")






