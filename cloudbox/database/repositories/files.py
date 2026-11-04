from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Favorite, File, Folder, User


@dataclass(slots=True)
class UserFileStats:
    files: int
    total_size: int
    sends: int
    favorites: int
    last_upload: datetime | None


@dataclass(slots=True)
class GlobalFileStats:
    users: int
    users_active: int
    files: int
    total_size: int
    folders: int


def _access_condition(user_id: int, accessible_folder_ids: set[int]):  # type: ignore[no-untyped-def]
    if accessible_folder_ids:
        return or_(
            File.owner_id == user_id,
            File.folder_id.in_(list(accessible_folder_ids)),
        )
    return File.owner_id == user_id


async def get(session: AsyncSession, file_id: int) -> File | None:
    return await session.get(File, file_id)


async def get_by_unique(
    session: AsyncSession, owner_id: int, file_unique_id: str
) -> File | None:
    return await session.scalar(
        select(File).where(
            File.owner_id == owner_id,
            File.file_unique_id == file_unique_id,
        )
    )


async def create(
    session: AsyncSession,
    *,
    owner_id: int,
    folder_id: int | None,
    file_id: str,
    file_unique_id: str,
    name: str,
    size: int,
    mime_type: str | None,
    kind: str,
    telegram_date: datetime | None,
) -> File:
    record = File(
        owner_id=owner_id,
        folder_id=folder_id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        name=name,
        name_lower=name.casefold(),
        size=size,
        mime_type=mime_type,
        kind=kind,
        telegram_date=telegram_date,
    )
    session.add(record)
    await session.flush()
    return record


async def list_by_folder(
    session: AsyncSession,
    *,
    folder_id: int | None,
    owner_id: int | None,
    offset: int,
    limit: int,
) -> list[File]:
    stmt = select(File)
    if folder_id is None:
        stmt = stmt.where(File.folder_id.is_(None))
        if owner_id is not None:
            stmt = stmt.where(File.owner_id == owner_id)
    else:
        stmt = stmt.where(File.folder_id == folder_id)
    stmt = stmt.order_by(File.uploaded_at.desc(), File.id.desc()).offset(offset).limit(limit)
    result = await session.scalars(stmt)
    return list(result.all())


async def count_by_folder(
    session: AsyncSession, *, folder_id: int | None, owner_id: int | None
) -> int:
    stmt = select(func.count(File.id))
    if folder_id is None:
        stmt = stmt.where(File.folder_id.is_(None))
        if owner_id is not None:
            stmt = stmt.where(File.owner_id == owner_id)
    else:
        stmt = stmt.where(File.folder_id == folder_id)
    return int(await session.scalar(stmt) or 0)


async def size_by_folder(
    session: AsyncSession, *, folder_id: int | None, owner_id: int | None
) -> int:
    stmt = select(func.coalesce(func.sum(File.size), 0))
    if folder_id is None:
        stmt = stmt.where(File.folder_id.is_(None))
        if owner_id is not None:
            stmt = stmt.where(File.owner_id == owner_id)
    else:
        stmt = stmt.where(File.folder_id == folder_id)
    return int(await session.scalar(stmt) or 0)


async def count_in_folders(session: AsyncSession, folder_ids: set[int]) -> int:
    if not folder_ids:
        return 0
    return int(
        await session.scalar(
            select(func.count(File.id)).where(File.folder_id.in_(list(folder_ids)))
        )
        or 0
    )


async def move_from_folders(
    session: AsyncSession, folder_ids: set[int], target_folder_id: int | None
) -> int:
    if not folder_ids:
        return 0
    result = await session.execute(
        update(File)
        .where(File.folder_id.in_(list(folder_ids)))
        .values(folder_id=target_folder_id)
    )
    return int(result.rowcount or 0)


async def delete_in_folders(session: AsyncSession, folder_ids: set[int]) -> int:
    if not folder_ids:
        return 0
    result = await session.execute(sql_delete(File).where(File.folder_id.in_(list(folder_ids))))
    return int(result.rowcount or 0)


async def rename(session: AsyncSession, record: File, name: str) -> None:
    record.name = name
    record.name_lower = name.casefold()
    await session.flush()


async def move(session: AsyncSession, record: File, folder_id: int | None) -> None:
    record.folder_id = folder_id
    await session.flush()


async def delete(session: AsyncSession, record: File) -> None:
    await session.delete(record)
    await session.flush()


async def increment_send_count(session: AsyncSession, file_id: int) -> None:
    await session.execute(
        update(File).where(File.id == file_id).values(send_count=File.send_count + 1)
    )


# --- Избранное -------------------------------------------------------------


async def is_favorite(session: AsyncSession, user_id: int, file_id: int) -> bool:
    return bool(
        await session.scalar(
            select(Favorite.id).where(
                Favorite.user_id == user_id,
                Favorite.file_id == file_id,
            )
        )
    )


async def add_favorite(session: AsyncSession, user_id: int, file_id: int) -> Favorite:
    favorite = Favorite(user_id=user_id, file_id=file_id)
    session.add(favorite)
    await session.flush()
    return favorite


async def remove_favorite(session: AsyncSession, user_id: int, file_id: int) -> None:
    await session.execute(
        sql_delete(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.file_id == file_id,
        )
    )


async def get_favorite(
    session: AsyncSession, user_id: int, file_id: int
) -> Favorite | None:
    return await session.scalar(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.file_id == file_id,
        )
    )


async def list_favorites(
    session: AsyncSession,
    *,
    user_id: int,
    accessible_folder_ids: set[int],
    offset: int,
    limit: int,
) -> list[File]:
    stmt = (
        select(File)
        .join(Favorite, Favorite.file_id == File.id)
        .where(
            Favorite.user_id == user_id,
            _access_condition(user_id, accessible_folder_ids),
        )
        .order_by(Favorite.created_at.desc(), File.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def count_favorites(
    session: AsyncSession, *, user_id: int, accessible_folder_ids: set[int]
) -> int:
    stmt = (
        select(func.count(Favorite.id))
        .join(File, File.id == Favorite.file_id)
        .where(
            Favorite.user_id == user_id,
            _access_condition(user_id, accessible_folder_ids),
        )
    )
    return int(await session.scalar(stmt) or 0)


# --- Поиск -----------------------------------------------------------------


async def search(
    session: AsyncSession,
    *,
    user_id: int,
    query_lower: str,
    accessible_folder_ids: set[int],
    offset: int,
    limit: int,
) -> list[File]:
    stmt = (
        select(File)
        .where(
            File.name_lower.contains(query_lower, autoescape=True),
            _access_condition(user_id, accessible_folder_ids),
        )
        .order_by(File.uploaded_at.desc(), File.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def count_search(
    session: AsyncSession,
    *,
    user_id: int,
    query_lower: str,
    accessible_folder_ids: set[int],
) -> int:
    stmt = select(func.count(File.id)).where(
        File.name_lower.contains(query_lower, autoescape=True),
        _access_condition(user_id, accessible_folder_ids),
    )
    return int(await session.scalar(stmt) or 0)


# --- Статистика ------------------------------------------------------------


async def stats_for_user(session: AsyncSession, user_id: int) -> UserFileStats:
    files, total_size, sends, last_upload = (
        await session.execute(
            select(
                func.count(File.id),
                func.coalesce(func.sum(File.size), 0),
                func.coalesce(func.sum(File.send_count), 0),
                func.max(File.uploaded_at),
            ).where(File.owner_id == user_id)
        )
    ).one()
    favorites = int(
        await session.scalar(
            select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
        )
        or 0
    )
    return UserFileStats(
        files=int(files or 0),
        total_size=int(total_size or 0),
        sends=int(sends or 0),
        favorites=favorites,
        last_upload=last_upload,
    )


async def global_stats(session: AsyncSession) -> GlobalFileStats:
    users = int(await session.scalar(select(func.count(User.id))) or 0)
    users_active = int(
        await session.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    )
    files, total_size = (
        await session.execute(
            select(
                func.count(File.id),
                func.coalesce(func.sum(File.size), 0),
            )
        )
    ).one()
    folders = int(await session.scalar(select(func.count(Folder.id))) or 0)
    return GlobalFileStats(
        users=users,
        users_active=users_active,
        files=int(files or 0),
        total_size=int(total_size or 0),
        folders=folders,
    )


async def users_with_file_stats(
    session: AsyncSession, offset: int, limit: int
) -> list[tuple[User, int, int]]:
    file_stats = (
        select(
            File.owner_id.label("owner_id"),
            func.count(File.id).label("files"),
            func.coalesce(func.sum(File.size), 0).label("size"),
        )
        .group_by(File.owner_id)
        .subquery()
    )
    stmt = (
        select(
            User,
            func.coalesce(file_stats.c.files, 0),
            func.coalesce(file_stats.c.size, 0),
        )
        .outerjoin(file_stats, file_stats.c.owner_id == User.id)
        .order_by(User.is_admin.desc(), User.created_at, User.id)
        .offset(offset)
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [(row[0], int(row[1]), int(row[2])) for row in rows.all()]
