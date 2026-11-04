from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..database.base import utcnow
from ..database.repositories import users as users_repo
from ..services import users as users_service

logger = logging.getLogger(__name__)

DENY_TEXT = (
    "⛔ <b>Доступ к CloudBox закрыт.</b>\n\n"
    "Ваш Telegram ID: <code>{tg_id}</code>\n"
    "Передайте его администратору, чтобы получить доступ."
)


class AccessMiddleware(BaseMiddleware):
    """Открывает сессию, проверяет пользователя и кладёт его в data["user"]."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._last_denied: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            from_user: TelegramUser | None = getattr(event, "from_user", None)

            chat_type = None
            if isinstance(event, Message):
                chat_type = event.chat.type
            elif isinstance(event, CallbackQuery) and event.message is not None:
                chat_type = event.message.chat.type

            if chat_type is not None and chat_type != "private":
                await session.rollback()
                await self._reject_chat(event)
                return None

            user = None
            if from_user is not None:
                user = await users_repo.get_by_tg_id(session, from_user.id)
                if user is not None and user.is_active:
                    await users_service.touch_user(
                        session,
                        user,
                        username=from_user.username,
                        full_name=from_user.full_name,
                    )
                    user.last_seen_at = utcnow()
                    data["user"] = user

            if user is None or not user.is_active:
                await session.rollback()
                await self._deny(event, from_user)
                return None

            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def _reject_chat(self, event: Message | CallbackQuery) -> None:
        text = "CloudBox работает только в личном чате с ботом."
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            else:
                await event.answer(text)
        except Exception:
            logger.debug("Не удалось отправить отказ для группового чата", exc_info=True)

    async def _deny(
        self, event: Message | CallbackQuery, from_user: TelegramUser | None
    ) -> None:
        tg_id = from_user.id if from_user is not None else 0
        now = time.monotonic()
        last = self._last_denied.get(tg_id, 0.0)
        if now - last < 10:
            return
        self._last_denied[tg_id] = now
        if len(self._last_denied) > 5000:
            self._last_denied.clear()

        text = DENY_TEXT.format(tg_id=tg_id)
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(text.replace("<b>", "").replace("</b>", ""), show_alert=True)
            else:
                await event.answer(text)
        except Exception:
            logger.debug("Не удалось отправить отказ в доступе", exc_info=True)
