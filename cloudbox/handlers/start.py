from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.callbacks import CancelCB, CommonCB
from ..keyboards.inline import cancel_keyboard
from ..keyboards.reply import (
    BTN_FAVORITES,
    BTN_FILES,
    BTN_FOLDERS,
    BTN_SEARCH,
    BTN_SETTINGS,
    BTN_STATS,
    BTN_UPLOAD,
    main_menu,
)
from ..states.forms import SearchForm
from . import views

router = Router(name="start")

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в CloudBox!</b>\n\n"
    "Это ваше личное файлохранилище внутри Telegram. Бот сохраняет "
    "идентификаторы файлов и метаданные, поэтому сами файлы остаются в "
    "Telegram, а вы в любой момент можете отправить их себе обратно.\n\n"
    "📤 Просто отправьте документ, фото, видео, аудио, голосовое сообщение, "
    "видеокружок или анимацию — файл появится в «Мои файлы».\n"
    "📂 Создавайте папки, добавляйте файлы в избранное и ищите по названию.\n\n"
    "Используйте меню ниже. Все команды доступны в /help."
)

HELP_TEXT = (
    "ℹ️ <b>Помощь по CloudBox</b>\n\n"
    "• Отправьте файл в чат — он сохранится в текущую папку (по умолчанию "
    "в корень).\n"
    "• «📁 Мои файлы» — каталог и папки.\n"
    "• «📂 Мои папки» — управление папками и доступом.\n"
    "• «⭐ Избранное» — отмеченные файлы.\n"
    "• «🔍 Поиск» — поиск по названию среди своих файлов и общих папок.\n"
    "• «📊 Статистика» — количество файлов, размер и другие цифры.\n\n"
    "<b>Команды:</b>\n"
    "/start — главное меню\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий ввод\n\n"
    "Файлы хранятся в Telegram. Удаление записи из каталога не удаляет "
    "файл из чата, но бот больше не сможет отправить его повторно."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✅ Действие отменено.", reply_markup=main_menu())


@router.message(F.text == BTN_FILES)
async def menu_files(
    message: Message, state: FSMContext, session: AsyncSession, user: User, config: Config
) -> None:
    await state.clear()
    await views.show_folder(message, session, user, config, None, edit=False)


@router.message(F.text == BTN_FOLDERS)
async def menu_folders(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    await views.show_folders_overview(message, session, user, edit=False)


@router.message(F.text == BTN_UPLOAD)
async def menu_upload(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    await views.show_upload_picker(message, session, user, edit=False)


@router.message(F.text == BTN_FAVORITES)
async def menu_favorites(
    message: Message, state: FSMContext, session: AsyncSession, user: User, config: Config
) -> None:
    await state.clear()
    await views.show_favorites(message, session, user, config, edit=False)


@router.message(F.text == BTN_SEARCH)
async def menu_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchForm.waiting)
    await message.answer(
        "🔍 <b>Поиск по файлам</b>\n\n"
        "Введите часть названия. Искать буду среди ваших файлов и файлов "
        "в общих папках, куда у вас есть доступ.",
        reply_markup=cancel_keyboard("main"),
    )


@router.message(F.text == BTN_STATS)
async def menu_stats(
    message: Message, state: FSMContext, session: AsyncSession, user: User, config: Config
) -> None:
    await state.clear()
    await views.show_stats(message, session, user, config, edit=False)


@router.message(F.text == BTN_SETTINGS)
async def menu_settings(
    message: Message, state: FSMContext, session: AsyncSession, user: User, config: Config
) -> None:
    await state.clear()
    await views.show_settings(message, session, user, config, edit=False)


@router.callback_query(CommonCB.filter(F.action == "noop"))
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(CommonCB.filter(F.action == "main"))
async def cb_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await views.show_main_menu(callback.message)


@router.callback_query(CommonCB.filter(F.action == "folders"))
async def cb_folders(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    if callback.message is not None:
        await views.show_folders_overview(callback.message, session, user)


@router.callback_query(CancelCB.filter(F.action == "main"))
async def cb_cancel_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await views.show_main_menu(callback.message)
