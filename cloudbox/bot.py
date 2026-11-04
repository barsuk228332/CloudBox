from __future__ import annotations

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .handlers import (
    admin,
    catalog,
    fallback,
    file_actions,
    folders,
    search,
    start,
    stats,
    upload,
)
from .handlers.errors import register_error_handler
from .middlewares.access import AccessMiddleware


def register_middlewares(
    dispatcher: Dispatcher,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    middleware = AccessMiddleware(session_factory)
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_routers(
        start.router,
        admin.router,
        folders.router,
        file_actions.router,
        catalog.router,
        search.router,
        stats.router,
        upload.router,
        fallback.router,
    )
    register_error_handler(dispatcher)
