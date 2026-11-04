from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from .utils.telegram import MAX_TG_ID, is_valid_tg_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///data/cloudbox.db"

load_dotenv(PROJECT_ROOT / ".env")

LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigError(RuntimeError):
    """Ошибка конфигурации приложения."""


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _parse_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = _env_str(name)
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} должен быть целым числом, получено: {raw!r}") from exc

    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} должен быть не меньше {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} должен быть не больше {maximum}")
    return value


def _parse_ids(name: str) -> tuple[int, ...]:
    raw = _env_str(name)
    if not raw:
        return ()

    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            tg_id = int(chunk)
        except ValueError as exc:
            raise ConfigError(f"{name}: {chunk!r} не является Telegram ID") from exc
        if tg_id <= 0:
            raise ConfigError(f"{name}: Telegram ID должен быть положительным")
        if not is_valid_tg_id(tg_id):
            raise ConfigError(f"{name}: Telegram ID слишком большой")
        if tg_id not in ids:
            ids.append(tg_id)
    return tuple(ids)


def _normalize_database_url(url: str) -> str:
    """Приводит sqlite URL к async-драйверу и абсолютному пути.

    Относительный путь в DATABASE_URL трактуется относительно корня проекта,
    а не текущего каталога процесса.
    """
    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
        url = "sqlite+aiosqlite:///" + url[len("sqlite:///") :]

    if url.startswith("sqlite+aiosqlite:///"):
        path = url[len("sqlite+aiosqlite:///") :]
        if path and path != ":memory:" and not Path(path).is_absolute():
            path = str((PROJECT_ROOT / path).resolve())
            url = "sqlite+aiosqlite:///" + path

    return url


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_id: int
    database_url: str
    allowed_ids: tuple[int, ...] = ()
    page_size: int = 8
    max_file_size_mb: int = 2000
    log_level: str = "INFO"
    timezone: str = "UTC"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls) -> Config:
        bot_token = _env_str("BOT_TOKEN")
        if not bot_token:
            raise ConfigError(
                "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
            )
        if ":" not in bot_token:
            raise ConfigError("BOT_TOKEN выглядит некорректно: ожидается формат '123456:ABC...'.")

        if not _env_str("ADMIN_ID"):
            raise ConfigError("ADMIN_ID не задан. Укажите Telegram ID администратора в .env.")

        admin_id = _parse_int("ADMIN_ID", 0, minimum=1, maximum=MAX_TG_ID)
        allowed_ids = _parse_ids("ALLOWED_IDS")
        database_url = _normalize_database_url(
            _env_str("DATABASE_URL") or DEFAULT_DATABASE_URL
        )

        page_size = _parse_int("PAGE_SIZE", 8, minimum=3, maximum=20)
        max_file_size_mb = _parse_int("MAX_FILE_SIZE_MB", 2000, minimum=1, maximum=4096)

        log_level = (_env_str("LOG_LEVEL") or "INFO").upper()
        if log_level not in LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL должен быть одним из: {', '.join(sorted(LOG_LEVELS))}")

        timezone = _env_str("TIMEZONE") or "UTC"
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f"Неизвестный часовой пояс TIMEZONE: {timezone!r}") from exc

        return cls(
            bot_token=bot_token,
            admin_id=admin_id,
            database_url=database_url,
            allowed_ids=allowed_ids,
            page_size=page_size,
            max_file_size_mb=max_file_size_mb,
            log_level=log_level,
            timezone=timezone,
        )
