from __future__ import annotations

import html
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

KIND_ICONS = {
    "document": "📄",
    "photo": "🖼",
    "video": "🎬",
    "audio": "🎵",
    "voice": "🎤",
    "video_note": "⭕️",
    "animation": "🎞",
}

KIND_LABELS = {
    "document": "Документ",
    "photo": "Фото",
    "video": "Видео",
    "audio": "Аудио",
    "voice": "Голосовое сообщение",
    "video_note": "Видеосообщение",
    "animation": "Анимация",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def truncate(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def human_size(size: int | None) -> str:
    size = max(0, int(size or 0))
    if size < 1024:
        return f"{size} Б"

    value = float(size)
    unit = "Б"
    for unit in ("КБ", "МБ", "ГБ", "ТБ"):
        value /= 1024
        if value < 1024 or unit == "ТБ":
            break

    if value >= 100:
        text = f"{value:.0f}"
    elif value >= 10:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} {unit}"


def format_dt(value: datetime | None, tz: ZoneInfo) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def kind_icon(kind: str) -> str:
    return KIND_ICONS.get(kind, "📎")


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, "Файл")
