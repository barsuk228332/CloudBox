from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


async def get_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    return await session.scalar(select(User).where(User.tg_id == tg_id))


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    username = username.lstrip("@").lower()
    if not username:
        return None
    return await session.scalar(select(User).where(func.lower(User.username) == username))


async def create(
    session: AsyncSession,
    tg_id: int,
    *,
    username: str | None = None,
    full_name: str = "",
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    user = User(
        tg_id=tg_id,
        username=username,
        full_name=full_name or f"Пользователь {tg_id}",
        is_admin=is_admin,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def list_page(session: AsyncSession, offset: int, limit: int) -> list[User]:
    result = await session.scalars(
        select(User).order_by(User.is_admin.desc(), User.created_at, User.id).offset(offset).limit(limit)
    )
    return list(result.all())


async def count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(User.id))) or 0)


async def list_all_active(session: AsyncSession) -> list[User]:
    result = await session.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.id)
    )
    return list(result.all())
