from __future__ import annotations

import asyncio
import logging
from typing import Final

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .bot import register_middlewares, register_routers
from .config import Config, ConfigError
from .database.engine import create_engine, create_session_factory, init_db
from .logging_config import setup_logging
from .services.albums import AlbumBuffer
from .services.users import seed_users

logger = logging.getLogger("cloudbox")

BOT_COMMANDS: Final = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="cancel", description="Отменить текущий ввод"),
]


async def run() -> None:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}")
        raise SystemExit(1) from exc

    setup_logging(config.log_level)

    engine = create_engine(config.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    await seed_users(
        session_factory,
        admin_id=config.admin_id,
        allowed_ids=config.allowed_ids,
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    album_buffer = AlbumBuffer()
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["config"] = config
    dispatcher["album_buffer"] = album_buffer

    register_middlewares(dispatcher, session_factory)
    register_routers(dispatcher)

    try:
        await bot.delete_webhook()
        await bot.set_my_commands(BOT_COMMANDS)
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError as exc:
            print("Ошибка: Telegram отклонил BOT_TOKEN. Проверьте токен в .env.")
            raise SystemExit(1) from exc
        logger.info("CloudBox запущен как @%s (id=%s)", me.username, me.id)
        logger.info("База данных: %s", config.database_url)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        logger.info("Останавливаю CloudBox…")
        await album_buffer.close()
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
