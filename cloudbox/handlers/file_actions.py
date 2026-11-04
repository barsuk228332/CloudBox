from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.callbacks import CancelCB, FileCB, MoveCB
from ..keyboards.inline import cancel_keyboard, confirm_delete_file_keyboard
from ..services import files as files_service
from ..states.forms import RenameFile
from ..utils.formatting import esc, human_size, kind_icon, truncate
from . import views

router = Router(name="file_actions")


async def _show_source(
    message: Message,
    *,
    src: str,
    page: int,
    folder_id: int,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    if src == "files":
        await views.show_folder(
            message, session, user, config, folder_id or None, page
        )
        return
    if src == "favs":
        await views.show_favorites(message, session, user, config, page)
        return
    if src == "search":
        data = await state.get_data()
        query = data.get("search_query")
        if query:
            await views.show_search_results(
                message, session, user, config, str(query), page
            )
            return
    await views.show_main_menu(message)


@router.callback_query(FileCB.filter(F.action == "send"))
async def send_file(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
) -> None:
    record = await files_service.get_for_read(session, user, callback_data.id)
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer("Отправляю файл…")
    await files_service.send_to_chat(
        session, callback.bot, callback.message.chat.id, record
    )


@router.callback_query(FileCB.filter(F.action.in_({"fav", "unfav"})))
async def toggle_favorite(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    state_now = await files_service.toggle_favorite(
        session, user, callback_data.id
    )
    await callback.answer(
        "⭐ Добавлено в избранное" if state_now else "Убрано из избранного"
    )
    if callback.message is not None:
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


@router.callback_query(FileCB.filter(F.action == "rename"))
async def ask_rename(
    callback: CallbackQuery,
    callback_data: FileCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    record = await files_service.get_owned(session, user, callback_data.id)
    await state.set_state(RenameFile.waiting)
    await state.update_data(
        file_id=record.id,
        page=callback_data.page,
        src=callback_data.src,
        folder=callback_data.folder,
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "✏️ <b>Переименование файла</b>\n\n"
            f"Текущее название: {esc(truncate(record.name, 100))}\n\n"
            "Отправьте новое название (до 255 символов).",
            reply_markup=cancel_keyboard(
                "file_card", id=record.id, page=callback_data.page
            ),
        )


@router.message(RenameFile.waiting, F.text)
async def submit_rename(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    data = await state.get_data()
    file_id = data.get("file_id")
    if not file_id:
        await state.clear()
        await message.answer("Состояние устарело. Откройте файл заново.")
        return

    record = await files_service.rename_file(
        session, user, int(file_id), message.text or ""
    )
    page = int(data.get("page") or 0)
    src = str(data.get("src") or "files")
    folder_id = int(data.get("folder") or 0)
    await state.clear()

    await message.answer("✅ Название обновлено.")
    await views.show_file_card(
        message,
        session,
        user,
        config,
        record.id,
        page=page,
        src=src,
        folder_id=folder_id,
        edit=False,
    )


@router.callback_query(FileCB.filter(F.action == "move"))
async def ask_move(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
) -> None:
    record = await files_service.get_owned(session, user, callback_data.id)
    await callback.answer()
    if callback.message is not None:
        await views.show_move_picker(
            callback.message, session, user, record, callback_data.page
        )


@router.callback_query(MoveCB.filter(F.action == "to"))
async def do_move(
    callback: CallbackQuery,
    callback_data: MoveCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    record = await files_service.move_file(
        session,
        user,
        callback_data.file_id,
        callback_data.folder_id or None,
    )
    await callback.answer("📂 Файл перемещён")
    if callback.message is not None:
        await views.show_file_card(
            callback.message,
            session,
            user,
            config,
            record.id,
            page=callback_data.page,
            src="files",
            folder_id=callback_data.folder_id,
        )


@router.callback_query(MoveCB.filter(F.action == "cancel"))
async def cancel_move(
    callback: CallbackQuery,
    callback_data: MoveCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    record = await files_service.get_for_read(session, user, callback_data.file_id)
    await callback.answer()
    if callback.message is not None:
        await views.show_file_card(
            callback.message,
            session,
            user,
            config,
            record.id,
            page=callback_data.page,
        )


@router.callback_query(FileCB.filter(F.action == "delete"))
async def ask_delete(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
) -> None:
    record, as_folder_owner = await files_service.get_for_delete(
        session, user, callback_data.id
    )
    await callback.answer()
    if callback.message is None:
        return

    text = (
        "🗑 <b>Удалить запись?</b>\n\n"
        f"{kind_icon(record.kind)} <b>{esc(record.name)}</b> "
        f"({human_size(record.size)})\n\n"
    )
    if as_folder_owner:
        text += (
            "Файл принадлежит другому пользователю. Вы удаляете запись как "
            "владелец папки: она исчезнет из каталога автора. Сам файл "
            "останется в Telegram."
        )
    else:
        text += (
            "Запись будет удалена из каталога. Файл останется в Telegram, "
            "но бот больше не сможет отправить его повторно."
        )

    await callback.message.edit_text(
        text,
        reply_markup=confirm_delete_file_keyboard(
            record.id,
            page=callback_data.page,
            src=callback_data.src,
            folder_id=callback_data.folder,
        ),
    )


@router.callback_query(FileCB.filter(F.action == "delyes"))
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: FileCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await files_service.delete_file(session, user, callback_data.id)
    await callback.answer("🗑 Запись удалена")
    if callback.message is None:
        return
    await _show_source(
        callback.message,
        src=callback_data.src,
        page=callback_data.page,
        folder_id=callback_data.folder,
        state=state,
        session=session,
        user=user,
        config=config,
    )


@router.callback_query(FileCB.filter(F.action == "delno"))
async def cancel_delete(
    callback: CallbackQuery,
    callback_data: FileCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is not None:
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


@router.callback_query(CancelCB.filter(F.action == "file_card"))
async def cancel_rename(
    callback: CallbackQuery,
    callback_data: CancelCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await views.show_file_card(
            callback.message,
            session,
            user,
            config,
            callback_data.id,
            page=callback_data.page,
        )
