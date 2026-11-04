from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import File, Folder, User
from ..database.repositories import folders as folders_repo
from ..database.repositories import users as users_repo
from ..keyboards.callbacks import AdminCB, CommonCB, NavCB
from ..keyboards.inline import (
    catalog_keyboard,
    file_card_keyboard,
    folders_overview_keyboard,
    move_keyboard,
    settings_keyboard,
    share_keyboard,
    upload_hint_keyboard,
    upload_picker_keyboard,
)
from ..keyboards.reply import main_menu
from ..services import access
from ..services import files as files_service
from ..services import folders as folders_service
from ..services import stats as stats_service
from ..utils.formatting import (
    esc,
    format_dt,
    human_size,
    kind_icon,
    kind_label,
    truncate,
)
from ..utils.pagination import clamp_page, offset_for, total_pages


async def render(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
    *,
    edit: bool,
) -> None:
    if edit:
        try:
            await message.edit_text(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
    await message.answer(
        text, reply_markup=keyboard, disable_web_page_preview=True
    )


async def _folder_label(session: AsyncSession, folder_id: int | None) -> str:
    if folder_id is None:
        return "Корень"
    names = await folders_service.folder_path_names(session, folder_id)
    return " / ".join(esc(name) for name in names) if names else "Корень"


async def show_main_menu(message: Message) -> None:
    text = (
        "🏠 <b>Главное меню CloudBox</b>\n\n"
        "Выберите раздел на клавиатуре ниже. Чтобы сохранить файл, просто "
        "отправьте его в чат."
    )
    await message.answer(text, reply_markup=main_menu())


async def show_folder(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    folder_id: int | None,
    page: int = 0,
    *,
    edit: bool = True,
) -> None:
    folder_access = None
    can_leave = False
    if folder_id is None:
        subfolders = await folders_repo.root_folders(session, user.id)
        can_manage = True
        can_upload = True
        is_shared = False
        title = "🏠 <b>Мои файлы</b>"
        path_text = ""
        back_cb = None
        current_id = 0
    else:
        folder_access = await access.require_folder_access(session, user, folder_id)
        folder = folder_access.folder
        subfolders = await folders_repo.children(session, folder.id)
        can_manage = folder_access.is_owner
        can_upload = folder_access.can_write
        is_shared = not folder_access.is_owner
        title = f"📂 <b>{esc(folder.name)}</b>"
        current_id = folder.id
        if can_manage:
            path_text = f"\n🧭 {await _folder_label(session, folder.id)}"
            back_cb = NavCB(
                scope="files", page=0, folder=folder.parent_id or 0
            ).pack()
        else:
            owner = await users_repo.get_by_id(session, folder.owner_id)
            owner_name = esc(owner.full_name if owner else "неизвестен")
            title = f"👥 <b>{esc(folder.name)}</b>"
            path_text = f"\n👤 Владелец: {owner_name}"
            can_leave = (
                folder_access.shared_from is not None
                and folder_access.shared_from.id == folder.id
            )
            parent_access = (
                await access.get_folder_access(session, user, folder.parent_id)
                if folder.parent_id is not None
                else None
            )
            if parent_access is not None:
                back_cb = NavCB(
                    scope="files", page=0, folder=folder.parent_id
                ).pack()
            else:
                back_cb = CommonCB(action="folders").pack()

    records, total, total_size = await files_service.folder_page(
        session,
        user,
        folder_id,
        offset=offset_for(page, config.page_size),
        limit=config.page_size,
    )
    pages = total_pages(total, config.page_size)
    clamped = clamp_page(page, pages)
    if clamped != page:
        page = clamped
        records, total, total_size = await files_service.folder_page(
            session,
            user,
            folder_id,
            offset=offset_for(page, config.page_size),
            limit=config.page_size,
        )

    summary = (
        f"📁 Подпапок: {len(subfolders)} · 📄 Файлов: {total} · "
        f"💾 {human_size(total_size)}"
    )
    text = f"{title}{path_text}\n{summary}"

    if not subfolders and total == 0:
        text += (
            "\n\nПока здесь пусто. Отправьте файл в чат"
            + (" или создайте папку." if can_manage else ".")
        )
    if len(subfolders) > 40:
        text += "\n\n<i>Показаны первые 40 папок.</i>"

    keyboard = catalog_keyboard(
        folders=subfolders,
        files=records,
        page=page,
        pages=pages,
        folder_id=current_id,
        src="files",
        can_manage=can_manage,
        can_upload=can_upload,
        back_cb=back_cb,
        is_shared=is_shared,
        can_leave=can_leave,
    )
    await render(message, text, keyboard, edit=edit)


async def show_folders_overview(
    message: Message, session: AsyncSession, user: User, *, edit: bool = True
) -> None:
    own = await folders_repo.root_folders(session, user.id)
    shared = await folders_service.list_shared_with_me(session, user)
    text = (
        "📂 <b>Мои папки</b>\n\n"
        f"📁 Своих: {len(own)} · 👥 Общих со мной: {len(shared)}"
    )
    if not own and not shared:
        text += "\n\nПапок пока нет. Создайте первую кнопкой ниже."
    if len(own) > 30 or len(shared) > 30:
        text += "\n\n<i>Показаны первые 30 папок в каждой категории.</i>"

    keyboard = folders_overview_keyboard(own, shared)
    await render(message, text, keyboard, edit=edit)


async def show_file_card(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    file_id: int,
    *,
    page: int = 0,
    src: str = "files",
    folder_id: int = 0,
    edit: bool = True,
) -> None:
    record = await files_service.get_for_read(session, user, file_id)
    favorite = await files_service.is_favorite(session, user, record.id)
    can_edit = record.owner_id == user.id
    can_delete = await access.can_delete_file(session, user, record)
    folder_label = await _folder_label(session, record.folder_id)

    lines = [
        f"{kind_icon(record.kind)} <b>{esc(record.name)}</b>",
        "",
        f"📏 Размер: {human_size(record.size)}",
        f"🏷 Тип: {kind_label(record.kind)}"
        + (f" ({esc(record.mime_type)})" if record.mime_type else ""),
        f"📂 Папка: {folder_label}",
        f"🕒 Загружен: {format_dt(record.uploaded_at, config.tzinfo)}",
        f"📤 Отправок: {record.send_count}",
    ]
    if record.owner_id != user.id:
        owner = await users_repo.get_by_id(session, record.owner_id)
        lines.append(f"👤 Автор: {esc(owner.full_name if owner else 'неизвестен')}")
    if favorite:
        lines.append("⭐ В избранном")

    keyboard = file_card_keyboard(
        record,
        page=page,
        src=src,
        folder_id=folder_id,
        is_favorite=favorite,
        can_edit=can_edit,
        can_delete=can_delete,
    )
    await render(message, "\n".join(lines), keyboard, edit=edit)


async def show_favorites(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    page: int = 0,
    *,
    edit: bool = True,
) -> None:
    records, total = await files_service.favorites_page(
        session,
        user,
        offset=offset_for(page, config.page_size),
        limit=config.page_size,
    )
    pages = total_pages(total, config.page_size)
    clamped = clamp_page(page, pages)
    if clamped != page:
        page = clamped
        records, total = await files_service.favorites_page(
            session,
            user,
            offset=offset_for(page, config.page_size),
            limit=config.page_size,
        )

    text = f"⭐ <b>Избранное</b>\n\nФайлов: {total}"
    if total == 0:
        text += (
            "\n\nПока пусто. Откройте карточку файла и нажмите "
            "«⭐ В избранное»."
        )

    keyboard = catalog_keyboard(
        folders=[],
        files=records,
        page=page,
        pages=pages,
        folder_id=0,
        src="favs",
        can_manage=False,
        can_upload=False,
        back_cb=None,
    )
    await render(message, text, keyboard, edit=edit)


async def show_search_results(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    query: str,
    page: int = 0,
    *,
    edit: bool = True,
) -> None:
    records, total = await files_service.search_files(
        session,
        user,
        query,
        offset=offset_for(page, config.page_size),
        limit=config.page_size,
    )
    pages = total_pages(total, config.page_size)
    clamped = clamp_page(page, pages)
    if clamped != page:
        page = clamped
        records, total = await files_service.search_files(
            session,
            user,
            query,
            offset=offset_for(page, config.page_size),
            limit=config.page_size,
        )

    text = f"🔍 <b>Поиск:</b> «{esc(truncate(query, 80))}»\n\nНайдено файлов: {total}"
    if total == 0:
        text += "\n\nПопробуйте другой запрос."

    keyboard = catalog_keyboard(
        folders=[],
        files=records,
        page=page,
        pages=pages,
        folder_id=0,
        src="search",
        can_manage=False,
        can_upload=False,
        back_cb=None,
    )
    await render(message, text, keyboard, edit=edit)


async def show_move_picker(
    message: Message,
    session: AsyncSession,
    user: User,
    record: File,
    page: int = 0,
    *,
    edit: bool = True,
) -> None:
    folders = await access.list_writable_folders(session, user)
    labelled: list[tuple[Folder, str]] = []
    for folder in folders:
        names = await folders_service.folder_path_names(session, folder.id)
        labelled.append((folder, " / ".join(names)))
    labelled.sort(key=lambda item: item[1].casefold())

    text = (
        f"📂 <b>Переместить файл</b>\n\n"
        f"{kind_icon(record.kind)} {esc(truncate(record.name, 80))}\n\n"
        "Выберите папку назначения. Список показывает все папки, куда вы "
        "можете добавлять файлы."
    )
    if len(labelled) > 40:
        text += "\n\n<i>Показаны первые 40 папок.</i>"
    keyboard = move_keyboard(record.id, labelled, page)
    await render(message, text, keyboard, edit=edit)


async def show_share_menu(
    message: Message,
    session: AsyncSession,
    user: User,
    folder_id: int,
    *,
    edit: bool = True,
) -> None:
    folder_access = await access.require_folder_owner(session, user, folder_id)
    folder = folder_access.folder
    entries = await folders_service.list_share_entries(session, user, folder_id)

    lines = [
        f"👥 <b>Доступ к папке «{esc(folder.name)}»</b>",
        "",
        (
            "По умолчанию доступ даёт чтение и отправку файлов. Нажмите "
            "👁/✏️, чтобы включить или выключить право загрузки."
        ),
    ]
    if entries:
        lines.append("")
        for share, grantee in entries[:20]:
            mode = "✏️ чтение + загрузка" if share.can_write else "👁 только чтение"
            username = f" (@{esc(grantee.username)})" if grantee.username else ""
            lines.append(
                f"• {esc(grantee.full_name)}{username} — {mode}"
            )
        if len(entries) > 20:
            lines.append(f"… и ещё {len(entries) - 20}")
    else:
        lines.append("\nПока доступ никому не выдан.")

    keyboard = share_keyboard(folder_id, entries)
    await render(message, "\n".join(lines), keyboard, edit=edit)


async def show_upload_picker(
    message: Message,
    session: AsyncSession,
    user: User,
    *,
    current_folder_id: int | None = None,
    edit: bool = True,
) -> None:
    folders = await access.list_writable_folders(session, user)
    labelled: list[tuple[Folder, str]] = []
    for folder in folders:
        names = await folders_service.folder_path_names(session, folder.id)
        labelled.append((folder, " / ".join(names)))
    labelled.sort(key=lambda item: item[1].casefold())

    text = (
        "📤 <b>Куда сохранять файлы?</b>\n\n"
        "Выберите папку назначения. После этого просто отправляйте файлы "
        "в чат — они будут сохранены туда."
    )
    if len(labelled) > 40:
        text += "\n\n<i>Показаны первые 40 папок.</i>"
    keyboard = upload_picker_keyboard(labelled, current_folder_id)
    await render(message, text, keyboard, edit=edit)


async def show_upload_hint(
    message: Message,
    session: AsyncSession,
    user: User,
    folder_id: int | None,
    *,
    edit: bool = True,
) -> None:
    folder_label = await _folder_label(session, folder_id)
    text = (
        "📤 <b>Загрузка файлов</b>\n\n"
        f"Файлы будут сохранены в: <b>{folder_label}</b>\n\n"
        "Отправьте документ, фото, видео, аудио, голосовое сообщение, "
        "видеокружок или анимацию. Можно отправить сразу несколько файлов."
    )
    keyboard = upload_hint_keyboard(folder_id)
    await render(message, text, keyboard, edit=edit)


async def show_stats(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    *,
    edit: bool = True,
) -> None:
    personal = await stats_service.personal(session, user)
    text = (
        "📊 <b>Ваша статистика</b>\n\n"
        f"📄 Файлов: {personal.files}\n"
        f"💾 Общий размер: {human_size(personal.total_size)}\n"
        f"📂 Папок: {personal.folders}\n"
        f"⭐ В избранном: {personal.favorites}\n"
        f"📤 Отправок: {personal.sends}\n"
        f"👥 Общих папок со мной: {personal.shared_with_me}\n"
        f"🔗 Моих папок с доступом: {personal.shared_by_me}\n"
        f"🕒 Последняя загрузка: {format_dt(personal.last_upload, config.tzinfo)}"
    )

    if user.is_admin:
        global_stats = await stats_service.global_(session)
        text += (
            "\n\n👑 <b>CloudBox целиком</b>\n"
            f"👤 Пользователей: {global_stats.users} "
            f"(активных {global_stats.users_active})\n"
            f"📄 Файлов: {global_stats.files}\n"
            f"💾 Размер: {human_size(global_stats.total_size)}\n"
            f"📂 Папок: {global_stats.folders}"
        )

    rows = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить", callback_data=CommonCB(action="stats").pack()
            )
        ]
    ]
    if user.is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👑 Админ-панель",
                    callback_data=AdminCB(action="panel").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Меню", callback_data=CommonCB(action="main").pack()
            )
        ]
    )
    await render(message, text, InlineKeyboardMarkup(inline_keyboard=rows), edit=edit)


async def show_settings(
    message: Message,
    session: AsyncSession,
    user: User,
    config: Config,
    *,
    edit: bool = True,
) -> None:
    personal = await stats_service.personal(session, user)
    role = "Администратор" if user.is_admin else "Пользователь"
    status = "активен" if user.is_active else "заблокирован"
    username = f"@{esc(user.username)}" if user.username else "—"
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"👤 Имя: {esc(user.full_name)}\n"
        f"🆔 Telegram ID: <code>{user.tg_id}</code>\n"
        f"🔗 Username: {username}\n"
        f"🎭 Роль: {role} ({status})\n\n"
        f"📦 В каталоге: {personal.files} файлов, "
        f"{human_size(personal.total_size)}\n"
        f"📤 Лимит файла: {config.max_file_size_mb} МБ\n"
        f"🕒 Часовой пояс: {config.timezone}"
    )
    await render(
        message, text, settings_keyboard(is_admin=user.is_admin), edit=edit
    )
