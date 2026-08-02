"""异步数据库 engine / session 工厂"""


from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker

)


from ..core.config import settings
#from app.core.config import settings

# 引擎
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True)

# 会话
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autocommit=False,
)

async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI依赖：提供请求级AsyncSession"""
    async with AsyncSessionLocal() as session:
        yield session




