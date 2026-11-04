from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Folder, FolderShare, User
from ..database.repositories import files as files_repo
from ..database.repositories import folders as folders_repo
from ..database.repositories import users as users_repo
from ..utils.telegram import is_valid_tg_id
from . import access
from .errors import AccessDenied, NotFoundError, ServiceError

MAX_FOLDER_DEPTH = 20
MAX_FOLDER_NAME = 120

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_name(raw: str, *, limit: int, what: str) -> str:
    cleaned = _CONTROL_CHARS.sub("", str(raw or ""))
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ServiceError(f"{what} не может быть пустым.")
    if len(cleaned) > limit:
        raise ServiceError(f"{what} длиннее {limit} символов.")
    if cleaned in {".", ".."}:
        raise ServiceError(f"Недопустимое название {what.lower()}.")
    return cleaned


@dataclass(frozen=True, slots=True)
class DeleteFolderResult:
    folders_deleted: int
    files_affected: int
    parent_id: int | None
    mode: str


async def create_folder(
    session: AsyncSession, user: User, parent_id: int | None, raw_name: str
) -> Folder:
    name = validate_name(raw_name, limit=MAX_FOLDER_NAME, what="Название папки")

    if parent_id is not None:
        parent_access = await access.get_folder_access(session, user, parent_id)
        if parent_access is None:
            raise NotFoundError("Родительская папка не найдена.")
        if not parent_access.is_owner:
            raise AccessDenied("Создавать подпапки может только владелец папки.")
        path = await access.folder_path(session, parent_id)
        if len(path) >= MAX_FOLDER_DEPTH:
            raise ServiceError(f"Максимальная вложенность папок — {MAX_FOLDER_DEPTH}.")

    existing = await folders_repo.find_by_name(
        session, user.id, parent_id, name.casefold()
    )
    if existing is not None:
        raise ServiceError("Папка с таким названием уже существует.")

    try:
        return await folders_repo.create(
            session, owner_id=user.id, parent_id=parent_id, name=name
        )
    except IntegrityError as exc:
        raise ServiceError("Не удалось создать папку: возможно, имя уже занято.") from exc


async def delete_preview(
    session: AsyncSession, user: User, folder_id: int
) -> tuple[Folder, int, int]:
    folder_access = await access.require_folder_owner(session, user, folder_id)
    ids = await folders_repo.descendant_ids(session, {folder_id})
    files_count = await files_repo.count_in_folders(session, ids)
    return folder_access.folder, max(0, len(ids) - 1), files_count


async def rename_folder(
    session: AsyncSession, user: User, folder_id: int, raw_name: str
) -> Folder:
    folder_access = await access.require_folder_owner(session, user, folder_id)
    folder = folder_access.folder
    name = validate_name(raw_name, limit=MAX_FOLDER_NAME, what="Название папки")

    existing = await folders_repo.find_by_name(
        session, user.id, folder.parent_id, name.casefold()
    )
    if existing is not None and existing.id != folder.id:
        raise ServiceError("Папка с таким названием уже существует.")

    await folders_repo.rename(session, folder, name)
    return folder


async def delete_folder(
    session: AsyncSession, user: User, folder_id: int, mode: str
) -> DeleteFolderResult:
    if mode not in {"move", "cascade"}:
        raise ServiceError("Неизвестный режим удаления папки.")

    folder_access = await access.require_folder_owner(session, user, folder_id)
    folder = folder_access.folder
    parent_id = folder.parent_id
    ids = await folders_repo.descendant_ids(session, {folder.id})

    if mode == "move":
        files_affected = await files_repo.move_from_folders(session, ids, parent_id)
    else:
        files_affected = await files_repo.delete_in_folders(session, ids)

    folders_deleted = await folders_repo.delete_many(session, ids)
    return DeleteFolderResult(
        folders_deleted=folders_deleted,
        files_affected=files_affected,
        parent_id=parent_id,
        mode=mode,
    )


async def add_share(
    session: AsyncSession, owner: User, folder_id: int, target_tg_id: int
) -> tuple[FolderShare, User, bool]:
    await access.require_folder_owner(session, owner, folder_id)

    if not is_valid_tg_id(target_tg_id):
        raise ServiceError("Некорректный Telegram ID пользователя.")

    if target_tg_id == owner.tg_id:
        raise ServiceError("Нельзя выдать доступ самому себе.")

    target = await users_repo.get_by_tg_id(session, target_tg_id)
    if target is None:
        raise ServiceError(
            "Пользователь не найден. Сначала добавьте его в белый список."
        )
    if not target.is_active:
        raise ServiceError("Пользователь заблокирован.")
    if target.id == owner.id:
        raise ServiceError("Нельзя выдать доступ самому себе.")

    existing = await folders_repo.share_for_user(session, folder_id, target.id)
    if existing is not None:
        return existing, target, False

    share = await folders_repo.add_share(session, folder_id, target.id)
    return share, target, True


async def set_share_write(
    session: AsyncSession,
    owner: User,
    folder_id: int,
    grantee_user_id: int,
    can_write: bool,
) -> FolderShare:
    await access.require_folder_owner(session, owner, folder_id)
    share = await folders_repo.share_for_user(session, folder_id, grantee_user_id)
    if share is None:
        raise NotFoundError("Доступ для этого пользователя не найден.")
    await folders_repo.set_share_write(session, share, can_write)
    return share


async def remove_share(
    session: AsyncSession, owner: User, folder_id: int, grantee_user_id: int
) -> None:
    await access.require_folder_owner(session, owner, folder_id)
    share = await folders_repo.share_for_user(session, folder_id, grantee_user_id)
    if share is None:
        raise NotFoundError("Доступ для этого пользователя не найден.")
    await folders_repo.remove_share(session, share)


async def leave_shared_folder(
    session: AsyncSession, user: User, folder_id: int
) -> None:
    share = await folders_repo.share_for_user(session, folder_id, user.id)
    if share is None:
        raise NotFoundError("Вы не являетесь получателем доступа к этой папке.")
    folder = await folders_repo.get(session, folder_id)
    if folder is not None and folder.owner_id == user.id:
        raise ServiceError("Нельзя покинуть собственную папку.")
    await folders_repo.remove_share(session, share)


async def list_share_entries(
    session: AsyncSession, user: User, folder_id: int
) -> list[tuple[FolderShare, User]]:
    await access.require_folder_owner(session, user, folder_id)
    return await folders_repo.list_shares(session, folder_id)


async def list_shared_with_me(session: AsyncSession, user: User) -> list[Folder]:
    return await folders_repo.shared_folders_for_user(session, user.id)


async def folder_path_names(session: AsyncSession, folder_id: int) -> list[str]:
    path = await access.folder_path(session, folder_id)
    return [folder.name for folder in path]


async def resolve_writable_folder(
    session: AsyncSession, user: User, folder_id: int | None
) -> Folder | None:
    if folder_id is None:
        return None
    folder_access = await access.get_folder_access(session, user, folder_id)
    if folder_access is None:
        raise AccessDenied("Папка не найдена или у вас нет к ней доступа.")
    if not folder_access.can_write:
        raise AccessDenied("В эту папку нельзя добавлять файлы.")
    return folder_access.folder
