from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)

from ..database.models import File
from ..utils.formatting import esc, truncate
from .errors import ServiceError

logger = logging.getLogger(__name__)


class SendFileError(ServiceError):
    pass


_METHODS: dict[str, tuple[str, str | None]] = {
    "photo": ("send_photo", "photo"),
    "video": ("send_video", "video"),
    "audio": ("send_audio", "audio"),
    "voice": ("send_voice", "voice"),
    "video_note": ("send_video_note", "video_note"),
    "animation": ("send_animation", "animation"),
    "document": ("send_document", "document"),
}

# Для этих типов Telegram не принимает caption.
_NO_CAPTION = {"video_note"}


def _caption(record: File) -> str | None:
    if record.kind in _NO_CAPTION:
        return None
    return esc(truncate(record.name, 900))


def _friendly_error(exc: TelegramAPIError) -> str:
    text = (getattr(exc, "message", "") or str(exc)).lower()
    if "too big" in text or "too large" in text or "file is too large" in text:
        return (
            "Telegram отказался отправлять файл: превышен лимит размера для ботов. "
            "Для больших файлов нужен локальный Bot API Server."
        )
    if "wrong file identifier" in text or "file reference" in text or "file_id" in text:
        return (
            "Telegram не принял file_id. Возможно, бот был пересоздан или сменился "
            "BOT_TOKEN — в этом случае файлы придётся загрузить заново."
        )
    if "chat not found" in text:
        return "Чат не найден. Напишите боту /start."
    if "bot was blocked" in text or "user is deactivated" in text:
        return "Бот заблокирован пользователем, отправка невозможна."
    if "retry after" in text:
        return "Telegram просит подождать перед повторной отправкой. Попробуйте через минуту."
    return "Telegram не смог отправить файл. Попробуйте ещё раз позже."


async def send_file(bot: Bot, chat_id: int, record: File) -> None:
    method_name, field = _METHODS.get(record.kind, _METHODS["document"])
    method = getattr(bot, method_name)
    caption = _caption(record)

    kwargs: dict[str, object] = {"chat_id": chat_id, field: record.file_id}
    if caption is not None:
        kwargs["caption"] = caption

    try:
        await method(**kwargs)
        return
    except TelegramBadRequest as exc:
        logger.warning(
            "Не удалось отправить файл %s как %s: %s", record.id, record.kind, exc
        )
        if method_name == "send_document":
            raise SendFileError(_friendly_error(exc)) from exc
    except TelegramForbiddenError as exc:
        logger.warning("Отправка файла %s запрещена: %s", record.id, exc)
        raise SendFileError(_friendly_error(exc)) from exc
    except TelegramAPIError as exc:
        logger.warning("Ошибка Telegram при отправке файла %s: %s", record.id, exc)
        raise SendFileError(_friendly_error(exc)) from exc

    # Fallback: некоторые типы не получается отправить нативным методом,
    # но тот же file_id может уйти как документ.
    try:
        kwargs = {"chat_id": chat_id, "document": record.file_id}
        if caption is not None:
            kwargs["caption"] = caption
        await bot.send_document(**kwargs)
    except TelegramAPIError as exc:
        logger.warning("Fallback-отправка файла %s не удалась: %s", record.id, exc)
        raise SendFileError(_friendly_error(exc)) from exc
