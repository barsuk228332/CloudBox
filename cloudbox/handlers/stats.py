from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.callbacks import CommonCB
from . import views

router = Router(name="stats")


@router.callback_query(CommonCB.filter(F.action == "stats"))
async def refresh_stats(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await views.show_stats(callback.message, session, user, config)
