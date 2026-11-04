from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.inline import cancel_keyboard
from ..states.forms import SearchForm
from . import views

router = Router(name="search")


@router.message(SearchForm.waiting, F.text)
async def submit_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer(
            "Введите непустой поисковый запрос.",
            reply_markup=cancel_keyboard("main"),
        )
        return
    if len(query) > 100:
        await message.answer(
            "Слишком длинный запрос: максимум 100 символов.",
            reply_markup=cancel_keyboard("main"),
        )
        return

    await state.set_state(SearchForm.results)
    await state.update_data(search_query=query)
    await views.show_search_results(
        message, session, user, config, query, edit=False
    )
