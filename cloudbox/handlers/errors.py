from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, ErrorEvent

from ..services.errors import ServiceError

logger = logging.getLogger(__name__)

GENERIC_ERROR = (
    "⚠️ Что-то пошло не так. Попробуйте ещё раз. "
    "Если ошибка повторяется, сообщите администратору."
)


def register_error_handler(dispatcher: Dispatcher) -> None:
    @dispatcher.errors()
    async def _handle_error(event: ErrorEvent) -> bool:
        exception = event.exception
        update = event.update

        if isinstance(exception, ServiceError):
            await _notify(update, exception.message, alert=True)
            return True

        logger.error(
            "Необработанная ошибка при обработке апдейта",
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        await _notify(update, GENERIC_ERROR, alert=False)
        return True


async def _notify(update, text: str, *, alert: bool) -> None:  # type: ignore[no-untyped-def]
    callback: CallbackQuery | None = getattr(update, "callback_query", None)
    if callback is not None:
        try:
            await callback.answer(text, show_alert=alert)
            return
        except Exception:
            logging.getLogger(__name__).debug(
                "Не удалось ответить на callback", exc_info=True
            )

    message = getattr(update, "message", None) or getattr(
        update, "edited_message", None
    )
    if message is not None:
        try:
            await message.answer(text)
        except Exception:
            logger.debug("Не удалось отправить сообщение об ошибке", exc_info=True)
