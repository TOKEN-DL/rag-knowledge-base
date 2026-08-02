"""FastAPI 依赖项汇总"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session


DbSession = Annotated[AsyncSession, Depends(get_session)]