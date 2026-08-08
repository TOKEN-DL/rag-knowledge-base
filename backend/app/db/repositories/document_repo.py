from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus

class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, document_id: UUID) -> Document | None:
        """通过ID查找文档"""
        return await self.session.get(Document, document_id)

    async def get_by_hash(self, file_hash: str) -> Document | None:
        """通过hash查找文档"""
        stmt = select(Document).where(Document.file_hash == file_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, document: Document) -> Document:
        """增加一个文档"""
        self.session.add(document)
        await self.session.flush()
        return document

    async def update_status(
            self,
            document_id: UUID,
            status: DocumentStatus,
            *,
            error_message: str | None = None,
    ) -> None:
        doc = await self.get_by_id(document_id)
        if doc is None:
            return
        doc.status = status

        if error_message is not None or status != DocumentStatus.FAILED:
            doc.error_message = error_message

    async def list_paginated(
            self,
            page: int,
            page_size: int,
            *,
            status: DocumentStatus | None = None,
    ) -> tuple[list[Document], int]:
        offset = (page - 1) * page_size
        # sql语句构造
        # 查询多个文档
        items_stmt = (
            select(Document)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        # 计算文档总数
        # .select_from() 必须挂在 select() 上，不能挂在 func.count() 上
        count_stmt = select(func.count()).select_from(Document)

        # 仅当传入了 status 才追加过滤条件；None 表示不过滤
        if status is not None:
            items_stmt = items_stmt.where(Document.status == status)
            count_stmt = count_stmt.where(Document.status == status)
        items = (await self.session.execute(items_stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items), int(total)

    async def delete(self, document: Document) -> None:
        """删除文档。chunks走ORM级联删除"""
        await self.session.delete(document)

