from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import File, Folder, User
from ..database.repositories import files as files_repo
from ..database.repositories import folders as folders_repo
from .errors import AccessDenied, NotFoundError


class AccessLevel(IntEnum):
    READ = 1
    WRITE = 2
    OWNER = 3


@dataclass(frozen=True, slots=True)
class FolderAccess:
    folder: Folder
    level: AccessLevel
    shared_from: Folder | None = None

    @property
    def can_read(self) -> bool:
        return self.level >= AccessLevel.READ

    @property
    def can_write(self) -> bool:
        return self.level >= AccessLevel.WRITE

    @property
    def is_owner(self) -> bool:
        return self.level == AccessLevel.OWNER


async def get_folder_access(
    session: AsyncSession, user: User, folder_id: int
) -> FolderAccess | None:
    folder = await folders_repo.get(session, folder_id)
    if folder is None:
        return None

    if folder.owner_id == user.id:
        return FolderAccess(folder=folder, level=AccessLevel.OWNER)

    best: AccessLevel | None = None
    shared_from: Folder | None = None
    current: Folder | None = folder
    seen: set[int] = set()

    for _ in range(64):
        if current is None or current.id in seen:
            break
        seen.add(current.id)

        share = await folders_repo.share_for_user(session, current.id, user.id)
        if share is not None:
            level = AccessLevel.WRITE if share.can_write else AccessLevel.READ
            if best is None or level > best:
                best = level
                shared_from = current
                if level == AccessLevel.WRITE:
                    break

        if current.parent_id is None:
            break
        current = await folders_repo.get(session, current.parent_id)

    if best is None:
        return None
    return FolderAccess(folder=folder, level=best, shared_from=shared_from)


async def require_folder_access(
    session: AsyncSession, user: User, folder_id: int, *, write: bool = False
) -> FolderAccess:
    access = await get_folder_access(session, user, folder_id)
    if access is None:
        raise AccessDenied("Папка не найдена или у вас нет к ней доступа.")
    if write and not access.can_write:
        raise AccessDenied("В эту папку нельзя добавлять файлы.")
    return access


async def require_folder_owner(
    session: AsyncSession, user: User, folder_id: int
) -> FolderAccess:
    access = await get_folder_access(session, user, folder_id)
    if access is None:
        raise NotFoundError("Папка не найдена.")
    if not access.is_owner:
        raise AccessDenied("Это действие доступно только владельцу папки.")
    return access


async def accessible_folder_ids(session: AsyncSession, user: User) -> set[int]:
    own = await folders_repo.all_owned_ids(session, user.id)
    shares = await folders_repo.shares_for_user(session, user.id)
    shared_roots = {share.folder_id for share in shares}
    return own | await folders_repo.descendant_ids(session, shared_roots)


async def writable_folder_ids(session: AsyncSession, user: User) -> set[int]:
    own = await folders_repo.all_owned_ids(session, user.id)
    shares = await folders_repo.shares_for_user(session, user.id)
    writable_roots = {share.folder_id for share in shares if share.can_write}
    return own | await folders_repo.descendant_ids(session, writable_roots)


async def list_writable_folders(session: AsyncSession, user: User) -> list[Folder]:
    ids = await writable_folder_ids(session, user)
    folders = await folders_repo.list_by_ids(session, ids)
    return sorted(folders, key=lambda folder: folder.name_lower)


async def folder_path(
    session: AsyncSession, folder_id: int, *, max_depth: int = 32
) -> list[Folder]:
    """Путь от корня до папки включительно."""
    chain: list[Folder] = []
    seen: set[int] = set()
    current = await folders_repo.get(session, folder_id)
    while current is not None and len(chain) < max_depth and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        if current.parent_id is None:
            break
        current = await folders_repo.get(session, current.parent_id)
    chain.reverse()
    return chain


async def can_read_file(session: AsyncSession, user: User, record: File) -> bool:
    if record.owner_id == user.id:
        return True
    if record.folder_id is None:
        return False
    return await get_folder_access(session, user, record.folder_id) is not None


async def require_read_file(
    session: AsyncSession, user: User, file_id: int
) -> File:
    record = await files_repo.get(session, file_id)
    if record is None:
        raise NotFoundError("Файл не найден.")
    if not await can_read_file(session, user, record):
        raise AccessDenied("У вас нет доступа к этому файлу.")
    return record


async def require_owned_file(
    session: AsyncSession, user: User, file_id: int
) -> File:
    record = await files_repo.get(session, file_id)
    if record is None:
        raise NotFoundError("Файл не найден.")
    if record.owner_id != user.id:
        raise AccessDenied("Это действие доступно только владельцу файла.")
    return record


async def can_delete_file(session: AsyncSession, user: User, record: File) -> bool:
    if record.owner_id == user.id:
        return True
    if record.folder_id is None:
        return False
    folder = await folders_repo.get(session, record.folder_id)
    return folder is not None and folder.owner_id == user.id


async def require_deletable_file(
    session: AsyncSession, user: User, file_id: int
) -> tuple[File, bool]:
    """Возвращает файл и признак «удаляет владелец папки, а не файла»."""
    record = await files_repo.get(session, file_id)
    if record is None:
        raise NotFoundError("Файл не найден.")
    if record.owner_id == user.id:
        return record, False
    if record.folder_id is not None:
        folder = await folders_repo.get(session, record.folder_id)
        if folder is not None and folder.owner_id == user.id:
            return record, True
    raise AccessDenied("Удалить этот файл может только его владелец или владелец папки.")
