from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram.types import Message

SUPPORTED_CONTENT_TYPES = (
    "document",
    "photo",
    "video",
    "audio",
    "voice",
    "video_note",
    "animation",
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FilePayload:
    file_id: str
    file_unique_id: str
    name: str
    size: int
    mime_type: str | None
    kind: str
    telegram_date: datetime | None


def sanitize_filename(name: str | None, fallback: str) -> str:
    cleaned = _CONTROL_CHARS.sub("", str(name or ""))
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        cleaned = fallback
    return cleaned[:255]


def _fallback_name(kind: str, stamp: str, extension: str) -> str:
    safe_kind = kind if kind != "video_note" else "video_note"
    return f"{safe_kind}_{stamp}.{extension}"


def extract_file_payload(message: Message) -> FilePayload | None:
    """Достаёт метаданные поддерживаемого вложения из сообщения Telegram."""
    kind = message.content_type
    if kind not in SUPPORTED_CONTENT_TYPES:
        return None

    stamp = (message.date or datetime.now(UTC)).strftime("%Y-%m-%d_%H-%M-%S")

    file_id: str
    unique_id: str
    name: str
    size: int
    mime_type: str | None

    if message.document:
        document = message.document
        file_id = document.file_id
        unique_id = document.file_unique_id
        size = document.file_size or 0
        mime_type = document.mime_type
        name = sanitize_filename(
            document.file_name, _fallback_name("document", stamp, "bin")
        )
    elif message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        unique_id = photo.file_unique_id
        size = photo.file_size or 0
        mime_type = "image/jpeg"
        name = _fallback_name("photo", stamp, "jpg")
    elif message.video:
        video = message.video
        file_id = video.file_id
        unique_id = video.file_unique_id
        size = video.file_size or 0
        mime_type = video.mime_type or "video/mp4"
        name = sanitize_filename(
            video.file_name, _fallback_name("video", stamp, "mp4")
        )
    elif message.audio:
        audio = message.audio
        file_id = audio.file_id
        unique_id = audio.file_unique_id
        size = audio.file_size or 0
        mime_type = audio.mime_type or "audio/mpeg"
        raw_name = audio.file_name
        if not raw_name and audio.title:
            raw_name = f"{audio.performer} - {audio.title}" if audio.performer else audio.title
        if raw_name and "." not in raw_name.rsplit("/", 1)[-1]:
            raw_name = f"{raw_name}.mp3"
        name = sanitize_filename(raw_name, _fallback_name("audio", stamp, "mp3"))
    elif message.voice:
        voice = message.voice
        file_id = voice.file_id
        unique_id = voice.file_unique_id
        size = voice.file_size or 0
        mime_type = voice.mime_type or "audio/ogg"
        name = _fallback_name("voice", stamp, "ogg")
    elif message.video_note:
        note = message.video_note
        file_id = note.file_id
        unique_id = note.file_unique_id
        size = note.file_size or 0
        mime_type = "video/mp4"
        name = _fallback_name("video_note", stamp, "mp4")
    elif message.animation:
        animation = message.animation
        file_id = animation.file_id
        unique_id = animation.file_unique_id
        size = animation.file_size or 0
        mime_type = animation.mime_type or "video/mp4"
        name = sanitize_filename(
            animation.file_name, _fallback_name("animation", stamp, "mp4")
        )
    else:
        return None

    telegram_date = message.date
    if telegram_date is not None and telegram_date.tzinfo is not None:
        telegram_date = telegram_date.astimezone(UTC).replace(tzinfo=None)

    return FilePayload(
        file_id=file_id,
        file_unique_id=unique_id,
        name=name,
        size=size,
        mime_type=mime_type,
        kind=kind,
        telegram_date=telegram_date,
    )
