from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..database.repositories import files as files_repo
from ..database.repositories import users as users_repo
from ..keyboards.callbacks import AdminCB, CancelCB
from ..keyboards.inline import (
    admin_panel_keyboard,
    admin_user_card_keyboard,
    admin_users_keyboard,
    cancel_keyboard,
)
from ..services import stats as stats_service
from ..services import users as users_service
from ..services.errors import AccessDenied, ServiceError
from ..states.forms import AdminAddUser
from ..utils.formatting import esc, format_dt, human_size
from ..utils.pagination import clamp_page, offset_for, total_pages
from . import views

router = Router(name="admin")

ADMIN_PAGE_SIZE = 8


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise AccessDenied("Эта команда доступна только администратору.")


async def _show_panel(
    message: Message, session: AsyncSession, user: User, *, edit: bool = True
) -> None:
    _require_admin(user)
    global_stats = await stats_service.global_(session)
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"👤 Пользователей: {global_stats.users} "
        f"(активных {global_stats.users_active})\n"
        f"📄 Файлов: {global_stats.files}\n"
        f"💾 Размер: {human_size(global_stats.total_size)}\n"
        f"📂 Папок: {global_stats.folders}"
    )
    await views.render(message, text, admin_panel_keyboard(), edit=edit)


async def _show_users(
    message: Message,
    session: AsyncSession,
    user: User,
    page: int,
    *,
    edit: bool = True,
) -> None:
    _require_admin(user)
    total = await users_repo.count(session)
    pages = total_pages(total, ADMIN_PAGE_SIZE)
    page = clamp_page(page, pages)
    rows = await files_repo.users_with_file_stats(
        session, offset_for(page, ADMIN_PAGE_SIZE), ADMIN_PAGE_SIZE
    )
    text = (
        "👥 <b>Пользователи</b>\n\n"
        f"Всего: {total} · Страница {page + 1}/{pages}\n\n"
        "Нажмите на пользователя, чтобы открыть карточку и изменить доступ."
    )
    keyboard = admin_users_keyboard(rows, page, pages)
    await views.render(message, text, keyboard, edit=edit)


async def _show_user_card(
    message: Message,
    session: AsyncSession,
    user: User,
    target_id: int,
    page: int,
    config: Config,
    *,
    edit: bool = True,
) -> None:
    _require_admin(user)
    target = await users_service.get_for_admin(session, target_id)
    stats = await stats_service.personal(session, target)
    username = f"@{esc(target.username)}" if target.username else "—"
    role = "Администратор" if target.is_admin else "Пользователь"
    status = "активен" if target.is_active else "заблокирован"

    text = (
        f"👤 <b>{esc(target.full_name)}</b>\n\n"
        f"🔗 Username: {username}\n"
        f"🆔 Telegram ID: <code>{target.tg_id}</code>\n"
        f"🎭 Роль: {role}\n"
        f"📌 Статус: {status}\n"
        f"📅 В боте с: {format_dt(target.created_at, config.tzinfo)}\n\n"
        f"📄 Файлов: {stats.files} ({human_size(stats.total_size)})\n"
        f"📂 Папок: {stats.folders}\n"
        f"⭐ В избранном: {stats.favorites}\n"
        f"📤 Отправок: {stats.sends}"
    )
    await views.render(
        message, text, admin_user_card_keyboard(target, page), edit=edit
    )


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession, user: User) -> None:
    await _show_users(message, session, user, 0, edit=False)


@router.message(Command("adduser"))
async def cmd_add_user(
    message: Message, session: AsyncSession, user: User
) -> None:
    _require_admin(user)
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        raise ServiceError("Использование: /adduser 123456789")
    tg_id = int(parts[1].strip())
    result = await users_service.add_user(session, tg_id)
    if result.created:
        await message.answer(
            f"✅ Пользователь <code>{tg_id}</code> добавлен в белый список."
        )
    elif result.reactivated:
        await message.answer(
            f"✅ Пользователь <code>{tg_id}</code> разблокирован."
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь <code>{tg_id}</code> уже есть в белом списке."
        )
    await _show_users(message, session, user, 0, edit=False)


@router.message(Command("deluser"))
async def cmd_del_user(
    message: Message, session: AsyncSession, user: User
) -> None:
    _require_admin(user)
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        raise ServiceError("Использование: /deluser 123456789")
    tg_id = int(parts[1].strip())
    target = await users_repo.get_by_tg_id(session, tg_id)
    if target is None:
        raise ServiceError("Пользователь с таким Telegram ID не найден.")
    await users_service.block_user(session, user, target)
    await message.answer(
        f"🚫 Пользователь <code>{tg_id}</code> заблокирован. "
        "Его файлы и папки сохранены."
    )


@router.message(Command("stats"))
async def cmd_admin_stats(
    message: Message, session: AsyncSession, user: User, config: Config
) -> None:
    _require_admin(user)
    await views.show_stats(message, session, user, config, edit=False)


@router.callback_query(AdminCB.filter(F.action == "panel"))
async def cb_panel(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    if callback.message is not None:
        await _show_panel(callback.message, session, user)


@router.callback_query(AdminCB.filter(F.action == "users"))
async def cb_users(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await _show_users(
            callback.message, session, user, callback_data.page
        )


@router.callback_query(AdminCB.filter(F.action == "user"))
async def cb_user(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await _show_user_card(
            callback.message,
            session,
            user,
            callback_data.user_id,
            callback_data.page,
            config,
        )


@router.callback_query(AdminCB.filter(F.action.in_({"block", "unblock"})))
async def cb_block(
    callback: CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    target = await users_service.get_for_admin(session, callback_data.user_id)
    if callback_data.action == "block":
        await users_service.block_user(session, user, target)
        await callback.answer("🚫 Пользователь заблокирован")
    else:
        await users_service.unblock_user(session, user, target)
        await callback.answer("✅ Пользователь разблокирован")
    if callback.message is not None:
        await _show_user_card(
            callback.message,
            session,
            user,
            target.id,
            callback_data.page,
            config,
        )


@router.callback_query(AdminCB.filter(F.action == "add"))
async def cb_add(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    _require_admin(user)
    await state.set_state(AdminAddUser.waiting)
    await state.update_data(admin_page=callback_data.page)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "➕ <b>Добавление пользователя</b>\n\n"
            "Отправьте числовой Telegram ID. Пользователь сразу получит доступ "
            "к боту.",
            reply_markup=cancel_keyboard("admin", page=callback_data.page),
        )


@router.message(AdminAddUser.waiting, F.text)
async def submit_add_user(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    _require_admin(user)
    raw = (message.text or "").strip().lstrip("+")
    if not raw.isdigit():
        raise ServiceError("Введите числовой Telegram ID, например 123456789.")

    result = await users_service.add_user(session, int(raw))
    data = await state.get_data()
    page = int(data.get("admin_page") or 0)
    await state.clear()

    if result.created:
        await message.answer(
            f"✅ Пользователь <code>{result.user.tg_id}</code> добавлен."
        )
    elif result.reactivated:
        await message.answer(
            f"✅ Пользователь <code>{result.user.tg_id}</code> разблокирован."
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь <code>{result.user.tg_id}</code> уже есть."
        )
    await _show_users(message, session, user, page, edit=False)


@router.callback_query(AdminCB.filter(F.action == "stats"))
async def cb_admin_stats(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await views.show_stats(callback.message, session, user, config)


@router.callback_query(CancelCB.filter(F.action == "admin"))
async def cb_cancel_admin(
    callback: CallbackQuery,
    callback_data: CancelCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await _show_users(
            callback.message, session, user, callback_data.page
        )
