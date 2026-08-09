from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AnswerCitation

class AnswerCitationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_add(self, citation: Sequence[AnswerCitation]):
        if not citation:
            return
        self.session.add_all(citation)
        await self.session.flush()
        
