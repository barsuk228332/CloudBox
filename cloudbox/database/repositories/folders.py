from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Folder, FolderShare, User


async def get(session: AsyncSession, folder_id: int) -> Folder | None:
    return await session.get(Folder, folder_id)


async def create(
    session: AsyncSession,
    *,
    owner_id: int,
    parent_id: int | None,
    name: str,
) -> Folder:
    folder = Folder(
        owner_id=owner_id,
        parent_id=parent_id,
        name=name,
        name_lower=name.casefold(),
    )
    session.add(folder)
    await session.flush()
    return folder


async def find_by_name(
    session: AsyncSession,
    owner_id: int,
    parent_id: int | None,
    name_lower: str,
) -> Folder | None:
    condition = Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    return await session.scalar(
        select(Folder).where(
            Folder.owner_id == owner_id,
            condition,
            Folder.name_lower == name_lower,
        )
    )


async def children(session: AsyncSession, parent_id: int) -> list[Folder]:
    result = await session.scalars(
        select(Folder)
        .where(Folder.parent_id == parent_id)
        .order_by(Folder.name_lower)
    )
    return list(result.all())


async def root_folders(session: AsyncSession, owner_id: int) -> list[Folder]:
    result = await session.scalars(
        select(Folder)
        .where(Folder.owner_id == owner_id, Folder.parent_id.is_(None))
        .order_by(Folder.name_lower)
    )
    return list(result.all())


async def count_owned(session: AsyncSession, owner_id: int) -> int:
    return int(
        await session.scalar(select(func.count(Folder.id)).where(Folder.owner_id == owner_id)) or 0
    )


async def all_owned_ids(session: AsyncSession, owner_id: int) -> set[int]:
    result = await session.scalars(select(Folder.id).where(Folder.owner_id == owner_id))
    return set(result.all())


async def list_by_ids(session: AsyncSession, folder_ids: set[int]) -> list[Folder]:
    if not folder_ids:
        return []
    result = await session.scalars(
        select(Folder).where(Folder.id.in_(list(folder_ids))).order_by(Folder.name_lower)
    )
    return list(result.all())


async def descendant_ids(session: AsyncSession, root_ids: set[int] | list[int]) -> set[int]:
    """Все id папок-потомков (включая сами корни) через рекурсивный CTE."""
    if not root_ids:
        return set()

    base = (
        select(Folder.id)
        .where(Folder.id.in_(list(root_ids)))
        .cte("folder_tree", recursive=True)
    )
    tree = base.union_all(
        select(Folder.id).join(base, Folder.parent_id == base.c.id)
    )
    result = await session.scalars(select(tree.c.id))
    return set(result.all())


async def rename(session: AsyncSession, folder: Folder, name: str) -> None:
    folder.name = name
    folder.name_lower = name.casefold()
    await session.flush()


async def delete_many(session: AsyncSession, folder_ids: set[int]) -> int:
    if not folder_ids:
        return 0
    result = await session.execute(delete(Folder).where(Folder.id.in_(list(folder_ids))))
    return int(result.rowcount or 0)


# --- Общий доступ ---------------------------------------------------------


async def share_for_user(
    session: AsyncSession, folder_id: int, user_id: int
) -> FolderShare | None:
    return await session.scalar(
        select(FolderShare).where(
            FolderShare.folder_id == folder_id,
            FolderShare.user_id == user_id,
        )
    )


async def add_share(
    session: AsyncSession, folder_id: int, user_id: int, can_write: bool = False
) -> FolderShare:
    share = FolderShare(folder_id=folder_id, user_id=user_id, can_write=can_write)
    session.add(share)
    await session.flush()
    return share


async def remove_share(session: AsyncSession, share: FolderShare) -> None:
    await session.delete(share)
    await session.flush()


async def list_shares(
    session: AsyncSession, folder_id: int
) -> list[tuple[FolderShare, User]]:
    rows = await session.execute(
        select(FolderShare, User)
        .join(User, User.id == FolderShare.user_id)
        .where(FolderShare.folder_id == folder_id)
        .order_by(User.full_name, User.id)
    )
    return [(row[0], row[1]) for row in rows.all()]


async def shared_folders_for_user(session: AsyncSession, user_id: int) -> list[Folder]:
    result = await session.scalars(
        select(Folder)
        .join(FolderShare, FolderShare.folder_id == Folder.id)
        .where(FolderShare.user_id == user_id)
        .order_by(Folder.name_lower)
    )
    return list(result.all())


async def shares_for_user(session: AsyncSession, user_id: int) -> list[FolderShare]:
    result = await session.scalars(
        select(FolderShare).where(FolderShare.user_id == user_id)
    )
    return list(result.all())


async def shares_by_owner(session: AsyncSession, owner_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(FolderShare.id))
            .join(Folder, Folder.id == FolderShare.folder_id)
            .where(Folder.owner_id == owner_id)
        )
        or 0
    )


async def shares_for_owner_user(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(FolderShare.id)).where(FolderShare.user_id == user_id)
        )
        or 0
    )


async def set_share_write(session: AsyncSession, share: FolderShare, can_write: bool) -> None:
    share.can_write = can_write
    await session.flush()
