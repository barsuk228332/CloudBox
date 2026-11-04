from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Текущее время в UTC без tzinfo — так его удобно хранить в SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_utc_naive(value: datetime) -> datetime:
    """Приводит datetime к naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Базовый класс моделей."""
