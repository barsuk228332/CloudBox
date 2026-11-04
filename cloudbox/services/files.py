from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import File, User
from ..database.repositories import files as files_repo
from ..utils.files import FilePayload
from ..utils.formatting import human_size
from . import access, sender
from . import folders as folders_service
from .errors import ServiceError


@dataclass(frozen=True, slots=True)
class UploadResult:
    record: File
    duplicate: bool
    folder_id: int | None


async def save_upload(
    session: AsyncSession,
    user: User,
    payload: FilePayload,
    *,
    folder_id: int | None,
    max_size_bytes: int,
) -> UploadResult:
    if payload.size > max_size_bytes:
        raise ServiceError(
            f"Файл слишком большой: {human_size(payload.size)}. "
            f"Лимит — {human_size(max_size_bytes)}."
        )

    if folder_id is not None:
        await folders_service.resolve_writable_folder(session, user, folder_id)

    existing = await files_repo.get_by_unique(
        session, user.id, payload.file_unique_id
    )
    if existing is not None:
        return UploadResult(record=existing, duplicate=True, folder_id=existing.folder_id)

    try:
        async with session.begin_nested():
            record = await files_repo.create(
                session,
                owner_id=user.id,
                folder_id=folder_id,
                file_id=payload.file_id,
                file_unique_id=payload.file_unique_id,
                name=payload.name,
                size=payload.size,
                mime_type=payload.mime_type,
                kind=payload.kind,
                telegram_date=payload.telegram_date,
            )
    except IntegrityError:
        existing = await files_repo.get_by_unique(
            session, user.id, payload.file_unique_id
        )
        if existing is None:
            raise ServiceError("Не удалось сохранить файл, попробуйте ещё раз.")
        return UploadResult(record=existing, duplicate=True, folder_id=existing.folder_id)

    return UploadResult(record=record, duplicate=False, folder_id=folder_id)


async def rename_file(
    session: AsyncSession, user: User, file_id: int, raw_name: str
) -> File:
    record = await access.require_owned_file(session, user, file_id)
    name = folders_service.validate_name(raw_name, limit=255, what="Название файла")
    await files_repo.rename(session, record, name)
    return record


async def move_file(
    session: AsyncSession, user: User, file_id: int, target_folder_id: int | None
) -> File:
    record = await access.require_owned_file(session, user, file_id)
    if target_folder_id is not None:
        await folders_service.resolve_writable_folder(session, user, target_folder_id)
    await files_repo.move(session, record, target_folder_id)
    return record


async def delete_file(
    session: AsyncSession, user: User, file_id: int
) -> tuple[File, bool]:
    record, as_folder_owner = await access.require_deletable_file(
        session, user, file_id
    )
    await files_repo.delete(session, record)
    return record, as_folder_owner


async def toggle_favorite(
    session: AsyncSession, user: User, file_id: int
) -> bool:
    record = await access.require_read_file(session, user, file_id)
    existing = await files_repo.get_favorite(session, user.id, record.id)
    if existing is not None:
        await files_repo.remove_favorite(session, user.id, record.id)
        return False
    await files_repo.add_favorite(session, user.id, record.id)
    return True


async def is_favorite(session: AsyncSession, user: User, file_id: int) -> bool:
    return await files_repo.is_favorite(session, user.id, file_id)


async def send_to_chat(session: AsyncSession, bot, chat_id: int, record: File) -> None:  # type: ignore[no-untyped-def]
    await sender.send_file(bot, chat_id, record)
    await files_repo.increment_send_count(session, record.id)
    record.send_count += 1


async def search_files(
    session: AsyncSession,
    user: User,
    query: str,
    *,
    offset: int,
    limit: int,
) -> tuple[list[File], int]:
    query = query.strip()
    if not query:
        raise ServiceError("Поисковый запрос не может быть пустым.")
    if len(query) > 100:
        raise ServiceError("Слишком длинный запрос: максимум 100 символов.")

    accessible_ids = await access.accessible_folder_ids(session, user)
    records = await files_repo.search(
        session,
        user_id=user.id,
        query_lower=query.casefold(),
        accessible_folder_ids=accessible_ids,
        offset=offset,
        limit=limit,
    )
    total = await files_repo.count_search(
        session,
        user_id=user.id,
        query_lower=query.casefold(),
        accessible_folder_ids=accessible_ids,
    )
    return records, total


async def favorites_page(
    session: AsyncSession,
    user: User,
    *,
    offset: int,
    limit: int,
) -> tuple[list[File], int]:
    accessible_ids = await access.accessible_folder_ids(session, user)
    records = await files_repo.list_favorites(
        session,
        user_id=user.id,
        accessible_folder_ids=accessible_ids,
        offset=offset,
        limit=limit,
    )
    total = await files_repo.count_favorites(
        session, user_id=user.id, accessible_folder_ids=accessible_ids
    )
    return records, total


async def folder_page(
    session: AsyncSession,
    user: User,
    folder_id: int | None,
    *,
    offset: int,
    limit: int,
) -> tuple[list[File], int, int]:
    if folder_id is not None:
        await access.require_folder_access(session, user, folder_id)

    total = await files_repo.count_by_folder(
        session, folder_id=folder_id, owner_id=user.id
    )
    total_size = await files_repo.size_by_folder(
        session, folder_id=folder_id, owner_id=user.id
    )
    records = await files_repo.list_by_folder(
        session,
        folder_id=folder_id,
        owner_id=user.id,
        offset=offset,
        limit=limit,
    )
    return records, total, total_size


async def get_for_read(
    session: AsyncSession, user: User, file_id: int
) -> File:
    return await access.require_read_file(session, user, file_id)


async def get_owned(session: AsyncSession, user: User, file_id: int) -> File:
    return await access.require_owned_file(session, user, file_id)


async def get_for_delete(
    session: AsyncSession, user: User, file_id: int
) -> tuple[File, bool]:
    return await access.require_deletable_file(session, user, file_id)
