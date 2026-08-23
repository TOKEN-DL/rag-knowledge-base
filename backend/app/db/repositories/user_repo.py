from uuid import UUID
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import  Role, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    #查找方法

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        stmt = (
            select(User)
            .where(User.username == username)
            .options(selectinload(User.roles))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_all(self) -> int:
        """启动期种子初始化用：库内无用户时才建 admin。"""
        return int(
            (await self.session.execute(select(func.count(User.id)))).scalar_one()
        )

    # 分页
    async def list_paginated(self, page: int, page_size: int) -> tuple[list[User], int]:
        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        offset = (page - 1) * page_size
        items_stmt = (
            select(User)
            .order_by(User.created_at.asc(), User.id.asc())
            .offset(offset)
            .limit(page_size)
            .options(selectinload(User.roles))
        )
        count_stmt = select(func.count(User.id))
        items = (await self.session.execute(items_stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def add(self, user: User) -> None:
        self.session.add(user)
        await self.session.flush()
        return user


    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()

    async def set_roles(self, user: User, roles: list[Role]) -> None:
        """整体替换用户角色集合。"""
        user.roles = roles
        await self.session.flush()


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, role_id: UUID) -> Role | None:
        return await self.session.get(Role, role_id)

    async def get_by_name(self, name: str) -> Role | None:
        stmt = (select(Role).where(Role.name == name))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        """角色总量天然小（教学项目不超过 10 个），不分页。"""
        stmt = select(Role).order_by(Role.created_at.asc(), Role.id.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_many(self, role_ids: Sequence[UUID]) -> list[Role]:
        if not role_ids:
            return []
        stmt = select(Role).where(Role.id.in_(list(role_ids)))
        return list((await self.session.execute(stmt)).scalars().all())

    async def add(self, role: Role) -> Role:
        self.session.add(role)
        await self.session.flush()
        return role

    async def delete(self, role: Role) -> None:
        await self.session.delete(role)
        await self.session.flush()
