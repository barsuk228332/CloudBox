from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..database.models import User
from ..database.repositories import users as users_repo
from ..utils.telegram import is_valid_tg_id
from .errors import AccessDenied, NotFoundError, ServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AddUserResult:
    user: User
    created: bool
    reactivated: bool


async def seed_users(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    admin_id: int,
    allowed_ids: tuple[int, ...] = (),
) -> None:
    """Создаёт администратора и стартовый белый список при первом запуске."""
    async with session_factory() as session:
        admin = await users_repo.get_by_tg_id(session, admin_id)
        if admin is None:
            try:
                async with session.begin_nested():
                    admin = await users_repo.create(
                        session,
                        admin_id,
                        full_name="Администратор",
                        is_admin=True,
                        is_active=True,
                    )
                logger.info("Создан администратор %s", admin_id)
            except IntegrityError:
                admin = await users_repo.get_by_tg_id(session, admin_id)
        else:
            changed = False
            if not admin.is_admin:
                admin.is_admin = True
                changed = True
            if not admin.is_active:
                admin.is_active = True
                changed = True
            if changed:
                logger.info("Полномочия администратора восстановлены для %s", admin_id)

        for tg_id in allowed_ids:
            if tg_id == admin_id:
                continue
            if await users_repo.get_by_tg_id(session, tg_id) is not None:
                continue
            try:
                async with session.begin_nested():
                    await users_repo.create(session, tg_id)
                logger.info("Добавлен пользователь из ALLOWED_IDS: %s", tg_id)
            except IntegrityError:
                logger.warning("Пользователь %s уже существует", tg_id)

        await session.commit()


async def touch_user(
    session: AsyncSession,
    user: User,
    *,
    username: str | None,
    full_name: str | None,
) -> None:
    changed = False
    if user.username != username:
        user.username = username
        changed = True
    if full_name and user.full_name != full_name:
        user.full_name = full_name
        changed = True
    if changed:
        await session.flush()


async def add_user(
    session: AsyncSession, tg_id: int, *, full_name: str | None = None
) -> AddUserResult:
    if not is_valid_tg_id(tg_id):
        raise ServiceError("Telegram ID должен быть положительным числом в допустимом диапазоне.")

    existing = await users_repo.get_by_tg_id(session, tg_id)
    if existing is not None:
        was_active = existing.is_active
        if not existing.is_active:
            existing.is_active = True
        if full_name and existing.full_name.startswith("Пользователь "):
            existing.full_name = full_name
        await session.flush()
        return AddUserResult(user=existing, created=False, reactivated=not was_active)

    try:
        async with session.begin_nested():
            created = await users_repo.create(session, tg_id, full_name=full_name or "")
    except IntegrityError:
        existing = await users_repo.get_by_tg_id(session, tg_id)
        if existing is None:
            raise ServiceError("Не удалось добавить пользователя, попробуйте ещё раз.")
        return AddUserResult(user=existing, created=False, reactivated=False)

    logger.info("Администратор добавил пользователя %s", tg_id)
    return AddUserResult(user=created, created=True, reactivated=False)


async def block_user(session: AsyncSession, actor: User, target: User) -> None:
    if not actor.is_admin:
        raise AccessDenied("Недостаточно прав.")
    if target.id == actor.id:
        raise ServiceError("Нельзя заблокировать самого себя.")
    if target.is_admin:
        raise ServiceError("Нельзя заблокировать администратора.")
    if not target.is_active:
        raise ServiceError("Пользователь уже заблокирован.")
    target.is_active = False
    await session.flush()
    logger.info("Пользователь %s заблокирован администратором %s", target.tg_id, actor.tg_id)


async def unblock_user(session: AsyncSession, actor: User, target: User) -> None:
    if not actor.is_admin:
        raise AccessDenied("Недостаточно прав.")
    if target.is_active:
        raise ServiceError("Пользователь уже активен.")
    target.is_active = True
    await session.flush()
    logger.info("Пользователь %s разблокирован администратором %s", target.tg_id, actor.tg_id)


async def get_active(session: AsyncSession, tg_id: int) -> User | None:
    user = await users_repo.get_by_tg_id(session, tg_id)
    if user is None or not user.is_active:
        return None
    return user


async def get_for_admin(session: AsyncSession, user_id: int) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден.")
    return user
