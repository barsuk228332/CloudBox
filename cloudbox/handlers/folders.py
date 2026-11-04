from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.callbacks import CancelCB, FolderCB, ShareCB, UploadCB
from ..keyboards.inline import cancel_keyboard, confirm_delete_folder_keyboard
from ..services import access
from ..services import folders as folders_service
from ..services.errors import ServiceError
from ..states.forms import CreateFolder, RenameFolder, ShareAdd
from ..utils.formatting import esc
from . import views

router = Router(name="folders")


@router.callback_query(FolderCB.filter(F.action == "open"))
async def open_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await views.show_folder(
            callback.message,
            session,
            user,
            config,
            callback_data.id or None,
        )


@router.callback_query(FolderCB.filter(F.action == "new"))
async def ask_create_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    parent_id = callback_data.id or None
    if parent_id is not None:
        await access.require_folder_owner(session, user, parent_id)
    await state.set_state(CreateFolder.waiting)
    await state.update_data(parent_id=parent_id)
    await callback.answer()
    if callback.message is not None:
        where = "в корне" if parent_id is None else "в текущей папке"
        await callback.message.answer(
            f"➕ <b>Новая папка</b>\n\nВведите название папки {where} "
            f"(до {folders_service.MAX_FOLDER_NAME} символов).",
            reply_markup=cancel_keyboard("folder", id=callback_data.id),
        )


@router.message(CreateFolder.waiting, F.text)
async def submit_create_folder(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    data = await state.get_data()
    parent_id = data.get("parent_id")
    folder = await folders_service.create_folder(
        session, user, parent_id, message.text or ""
    )
    await state.clear()
    await message.answer(f"✅ Папка «{esc(folder.name)}» создана.")
    await views.show_folder(
        message, session, user, config, parent_id, edit=False
    )


@router.callback_query(FolderCB.filter(F.action == "rename"))
async def ask_rename_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    folder_access = await access.require_folder_owner(
        session, user, callback_data.id
    )
    await state.set_state(RenameFolder.waiting)
    await state.update_data(folder_id=folder_access.folder.id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "✏️ <b>Переименование папки</b>\n\n"
            f"Текущее название: {esc(folder_access.folder.name)}\n\n"
            "Отправьте новое название.",
            reply_markup=cancel_keyboard("folder", id=folder_access.folder.id),
        )


@router.message(RenameFolder.waiting, F.text)
async def submit_rename_folder(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    data = await state.get_data()
    folder_id = data.get("folder_id")
    if not folder_id:
        await state.clear()
        await message.answer("Состояние устарело. Откройте папку заново.")
        return
    folder = await folders_service.rename_folder(
        session, user, int(folder_id), message.text or ""
    )
    await state.clear()
    await message.answer("✅ Папка переименована.")
    await views.show_folder(message, session, user, config, folder.id, edit=False)


@router.callback_query(FolderCB.filter(F.action == "delete"))
async def ask_delete_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    session: AsyncSession,
    user: User,
) -> None:
    folder, subfolders, files_count = await folders_service.delete_preview(
        session, user, callback_data.id
    )
    await callback.answer()
    if callback.message is None:
        return
    text = (
        f"🗑 <b>Удалить папку «{esc(folder.name)}»?</b>\n\n"
        f"Внутри: {files_count} файлов, {subfolders} подпапок.\n\n"
        "📤 <b>Файлы наверх</b> — все записи сохранятся и переедут в "
        "родительскую папку (или в корень).\n"
        "🗑 <b>Удалить всё</b> — записи файлов будут удалены. Сами файлы "
        "останутся в Telegram, но бот больше не сможет их отправить."
    )
    await callback.message.edit_text(
        text, reply_markup=confirm_delete_folder_keyboard(folder.id)
    )


@router.callback_query(FolderCB.filter(F.action.in_({"del_move", "del_cascade"})))
async def delete_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    mode = "move" if callback_data.action == "del_move" else "cascade"
    result = await folders_service.delete_folder(
        session, user, callback_data.id, mode
    )
    if mode == "move":
        await callback.answer(f"📤 Перенесено файлов: {result.files_affected}")
    else:
        await callback.answer(f"🗑 Удалено записей: {result.files_affected}")
    if callback.message is not None:
        await views.show_folder(
            callback.message,
            session,
            user,
            config,
            result.parent_id,
        )


@router.callback_query(FolderCB.filter(F.action == "share"))
async def open_share_menu(
    callback: CallbackQuery,
    callback_data: FolderCB,
    session: AsyncSession,
    user: User,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await views.show_share_menu(
            callback.message, session, user, callback_data.id
        )


@router.callback_query(FolderCB.filter(F.action == "upload"))
async def set_upload_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    folder_id = callback_data.id or None
    if folder_id is not None:
        await access.require_folder_access(session, user, folder_id, write=True)
    await state.update_data(upload_folder_id=folder_id)
    await callback.answer()
    if callback.message is not None:
        await views.show_upload_hint(
            callback.message, session, user, folder_id
        )


@router.callback_query(FolderCB.filter(F.action == "leave"))
async def leave_folder(
    callback: CallbackQuery,
    callback_data: FolderCB,
    session: AsyncSession,
    user: User,
) -> None:
    await folders_service.leave_shared_folder(session, user, callback_data.id)
    await callback.answer("Вы покинули общую папку")
    if callback.message is not None:
        await views.show_folders_overview(callback.message, session, user)


@router.callback_query(ShareCB.filter(F.action == "add"))
async def ask_share_add(
    callback: CallbackQuery,
    callback_data: ShareCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await access.require_folder_owner(session, user, callback_data.folder_id)
    await state.set_state(ShareAdd.waiting)
    await state.update_data(folder_id=callback_data.folder_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "👥 <b>Доступ к папке</b>\n\n"
            "Отправьте числовой Telegram ID пользователя. Он должен быть "
            "добавлен в белый список бота.",
            reply_markup=cancel_keyboard("share", id=callback_data.folder_id),
        )


@router.message(ShareAdd.waiting, F.text)
async def submit_share_add(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
) -> None:
    data = await state.get_data()
    folder_id = data.get("folder_id")
    if not folder_id:
        await state.clear()
        await message.answer("Состояние устарело. Откройте папку заново.")
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        raise ServiceError("Введите числовой Telegram ID, например 123456789.")
    tg_id = int(raw)

    _share, target, created = await folders_service.add_share(
        session, user, int(folder_id), tg_id
    )
    await state.clear()
    if created:
        await message.answer(
            f"✅ Доступ к папке выдан пользователю {esc(target.full_name)} "
            f"(<code>{target.tg_id}</code>)."
        )
    else:
        await message.answer(
            f"ℹ️ У пользователя {esc(target.full_name)} уже есть доступ."
        )
    await views.show_share_menu(
        message, session, user, int(folder_id), edit=False
    )


@router.callback_query(ShareCB.filter(F.action == "toggle"))
async def toggle_share_write(
    callback: CallbackQuery,
    callback_data: ShareCB,
    session: AsyncSession,
    user: User,
) -> None:
    share = await folders_service.set_share_write(
        session,
        user,
        callback_data.folder_id,
        callback_data.user_id,
        not bool(
            await _share_can_write(
                session, callback_data.folder_id, callback_data.user_id
            )
        ),
    )
    await callback.answer(
        "✏️ Разрешена загрузка" if share.can_write else "👁 Только чтение"
    )
    if callback.message is not None:
        await views.show_share_menu(
            callback.message, session, user, callback_data.folder_id
        )


async def _share_can_write(
    session: AsyncSession, folder_id: int, user_id: int
) -> bool:
    from ..database.repositories import folders as folders_repo

    share = await folders_repo.share_for_user(session, folder_id, user_id)
    return bool(share and share.can_write)


@router.callback_query(ShareCB.filter(F.action == "remove"))
async def remove_share(
    callback: CallbackQuery,
    callback_data: ShareCB,
    session: AsyncSession,
    user: User,
) -> None:
    await folders_service.remove_share(
        session, user, callback_data.folder_id, callback_data.user_id
    )
    await callback.answer("Доступ отозван")
    if callback.message is not None:
        await views.show_share_menu(
            callback.message, session, user, callback_data.folder_id
        )


@router.callback_query(CancelCB.filter(F.action == "folder"))
async def cancel_folder_input(
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
        await views.show_folder(
            callback.message,
            session,
            user,
            config,
            callback_data.id or None,
        )


@router.callback_query(CancelCB.filter(F.action == "share"))
async def cancel_share_input(
    callback: CallbackQuery,
    callback_data: CancelCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await views.show_share_menu(
            callback.message, session, user, callback_data.id
        )


@router.callback_query(UploadCB.filter(F.action == "pick"))
async def pick_upload_folder(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    data = await state.get_data()
    await callback.answer()
    if callback.message is not None:
        await views.show_upload_picker(
            callback.message,
            session,
            user,
            current_folder_id=data.get("upload_folder_id"),
        )


@router.callback_query(UploadCB.filter(F.action == "set"))
async def select_upload_folder(
    callback: CallbackQuery,
    callback_data: UploadCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    folder_id = callback_data.folder_id or None
    if folder_id is not None:
        await access.require_folder_access(session, user, folder_id, write=True)
    await state.update_data(upload_folder_id=folder_id)
    await callback.answer("Папка выбрана")
    if callback.message is not None:
        await views.show_upload_hint(
            callback.message, session, user, folder_id
        )


@router.callback_query(UploadCB.filter(F.action == "done"))
async def finish_upload(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Готово")
    if callback.message is not None:
        await views.show_main_menu(callback.message)
