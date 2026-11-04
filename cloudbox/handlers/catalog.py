from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.callbacks import FileCB, NavCB
from . import views

router = Router(name="catalog")


@router.callback_query(NavCB.filter(F.scope == "files"))
async def nav_files(
    callback: CallbackQuery,
    callback_data: NavCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await views.show_folder(
        callback.message,
        session,
        user,
        config,
        callback_data.folder or None,
        callback_data.page,
    )


@router.callback_query(NavCB.filter(F.scope == "favs"))
async def nav_favorites(
    callback: CallbackQuery,
    callback_data: NavCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await views.show_favorites(
        callback.message, session, user, config, callback_data.page
    )


@router.callback_query(NavCB.filter(F.scope == "search"))
async def nav_search(
    callback: CallbackQuery,
    callback_data: NavCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    query = data.get("search_query")
    if not query:
        await callback.answer(
            "Поиск устарел. Начните его заново через меню «🔍 Поиск».",
            show_alert=True,
        )
        return
    await callback.answer()
    await views.show_search_results(
        callback.message, session, user, config, str(query), callback_data.page
    )


@router.callback_query(NavCB.filter(F.scope == "folders"))
async def nav_folders(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await views.show_folders_overview(callback.message, session, user)


@router.callback_query(FileCB.filter(F.action == "card"))
async def show_card(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await views.show_file_card(
        callback.message,
        session,
        user,
        config,
        callback_data.id,
        page=callback_data.page,
        src=callback_data.src,
        folder_id=callback_data.folder,
    )
