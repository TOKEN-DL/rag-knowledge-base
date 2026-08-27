from uuid import UUID

from sqlalchemy import func, select, ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus

from app.db.repositories.chunk_repo import _permission_where
from datetime import datetime

class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, document_id: UUID, *, permission_tags: list[str] | None = None,) -> Document | None:
        """通过ID查找文档 非 None permission_tags 时叠加可见性过滤。"""
        if permission_tags is None:
            return await self.session.get(Document, document_id)
        perm_where = _permission_where(permission_tags)
        stmt = select(Document).where(Document.id == document_id)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return (await self.session.execute(stmt)).scalar_one_or_none()



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
            permission_tags: list[str] | None = None
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

        perm_where: ColumnElement[bool] | None = _permission_where(permission_tags)
        if perm_where is not None:
            items_stmt = items_stmt.where(perm_where)
            count_stmt = count_stmt.where(perm_where)
        items = (await self.session.execute(items_stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(items), int(total)


    async def delete(self, document: Document) -> None:
        """删除文档。chunks走ORM级联删除"""
        await self.session.delete(document)


    async def count(
            self,
            *,
            permission_tags: list[str] | None = None,
    ) -> int:
        """统计可见文档总数。MCP get_knowledge_base_stats 用。"""
        stmt = select(func.count()).select_from(Document)
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return int((await self.session.execute(stmt)).scalar_one())


    async def get_last_indexed_at(
            self,
            *,
            permission_tags: list[str] | None = None,
    ) -> datetime | None:
        """最近一次进入 ready 状态的文档时间。

        用 updated_at 而非 created_at：reindex 成功后 updated_at 会刷新，
        外部 Agent 看到的"最近一次入库"含义里包含增量重建。
        """

        stmt = select(func.max(Document.updated_at)).where(
            Document.status == DocumentStatus.READY
        )
        perm_where = _permission_where(permission_tags)
        if perm_where is not None:
            stmt = stmt.where(perm_where)
        return (await self.session.execute(stmt)).scalar_one_or_none()



