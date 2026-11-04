from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import User
from ..database.repositories import files as files_repo
from ..database.repositories import folders as folders_repo
from ..database.repositories.files import GlobalFileStats
from . import access


@dataclass(frozen=True, slots=True)
class PersonalStats:
    files: int
    total_size: int
    sends: int
    favorites: int
    last_upload: datetime | None
    folders: int
    shared_with_me: int
    shared_by_me: int


async def personal(session: AsyncSession, user: User) -> PersonalStats:
    file_stats = await files_repo.stats_for_user(session, user.id)
    accessible_ids = await access.accessible_folder_ids(session, user)
    favorites = await files_repo.count_favorites(
        session, user_id=user.id, accessible_folder_ids=accessible_ids
    )
    return PersonalStats(
        files=file_stats.files,
        total_size=file_stats.total_size,
        sends=file_stats.sends,
        favorites=favorites,
        last_upload=file_stats.last_upload,
        folders=await folders_repo.count_owned(session, user.id),
        shared_with_me=await folders_repo.shares_for_owner_user(session, user.id),
        shared_by_me=await folders_repo.shares_by_owner(session, user.id),
    )


async def global_(session: AsyncSession) -> GlobalFileStats:
    return await files_repo.global_stats(session)
