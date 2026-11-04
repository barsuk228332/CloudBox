from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..database.models import File, Folder, FolderShare, User
from ..utils.formatting import human_size, kind_icon, truncate
from .callbacks import (
    AdminCB,
    CancelCB,
    CommonCB,
    FileCB,
    FolderCB,
    MoveCB,
    NavCB,
    ShareCB,
    UploadCB,
)


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _pagination_row(scope: str, page: int, pages: int, folder: int = 0) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(
            _button(
                "⬅️",
                NavCB(scope=scope, page=page - 1, folder=folder).pack(),
            )
        )
    row.append(_button(f"{page + 1}/{pages}", CommonCB(action="noop").pack()))
    if page + 1 < pages:
        row.append(
            _button(
                "➡️",
                NavCB(scope=scope, page=page + 1, folder=folder).pack(),
            )
        )
    return row


def catalog_keyboard(
    *,
    folders: list[Folder],
    files: list[File],
    page: int,
    pages: int,
    folder_id: int,
    src: str,
    can_manage: bool,
    can_upload: bool,
    back_cb: str | None,
    is_shared: bool = False,
    can_leave: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for folder in folders[:40]:
        prefix = "👥" if is_shared else "📂"
        rows.append(
            [
                _button(
                    f"{prefix} {truncate(folder.name, 40)}",
                    FolderCB(action="open", id=folder.id).pack(),
                )
            ]
        )

    for record in files:
        rows.append(
            [
                _button(
                    f"{kind_icon(record.kind)} {truncate(record.name, 34)} · {human_size(record.size)}",
                    FileCB(
                        action="card",
                        id=record.id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                )
            ]
        )

    if pages > 1:
        rows.append(_pagination_row(src, page, pages, folder_id))

    if can_manage:
        if folder_id:
            rows.append(
                [
                    _button("➕ Подпапка", FolderCB(action="new", id=folder_id).pack()),
                    _button("👥 Доступ", FolderCB(action="share", id=folder_id).pack()),
                ]
            )
            rows.append(
                [
                    _button(
                        "✏️ Переименовать",
                        FolderCB(action="rename", id=folder_id).pack(),
                    ),
                    _button("🗑 Удалить", FolderCB(action="delete", id=folder_id).pack()),
                ]
            )
        else:
            rows.append(
                [_button("➕ Новая папка", FolderCB(action="new", id=0).pack())]
            )

    if can_upload:
        rows.append(
            [
                _button(
                    "📤 Загрузить сюда",
                    FolderCB(action="upload", id=folder_id).pack(),
                )
            ]
        )

    if can_leave and folder_id:
        rows.append(
            [
                _button(
                    "🚪 Покинуть папку",
                    FolderCB(action="leave", id=folder_id).pack(),
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if back_cb:
        nav.append(_button("⬅️ Назад", back_cb))
    nav.append(_button("🏠 Меню", CommonCB(action="main").pack()))
    rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def file_card_keyboard(
    record: File,
    *,
    page: int,
    src: str,
    folder_id: int,
    is_favorite: bool,
    can_edit: bool,
    can_delete: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            _button(
                "📤 Отправить",
                FileCB(
                    action="send", id=record.id, page=page, src=src, folder=folder_id
                ).pack(),
            ),
            _button(
                "💔 Убрать" if is_favorite else "⭐ В избранное",
                FileCB(
                    action="unfav" if is_favorite else "fav",
                    id=record.id,
                    page=page,
                    src=src,
                    folder=folder_id,
                ).pack(),
            ),
        ]
    ]

    if can_edit:
        rows.append(
            [
                _button(
                    "✏️ Переименовать",
                    FileCB(
                        action="rename",
                        id=record.id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                ),
                _button(
                    "📂 Переместить",
                    FileCB(
                        action="move",
                        id=record.id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                ),
            ]
        )

    if can_delete:
        rows.append(
            [
                _button(
                    "🗑 Удалить",
                    FileCB(
                        action="delete",
                        id=record.id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            _button(
                "⬅️ К списку",
                NavCB(scope=src, page=page, folder=folder_id).pack(),
            ),
            _button("🏠 Меню", CommonCB(action="main").pack()),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upload_result_keyboard(
    record_id: int, *, folder_id: int, duplicate: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            _button(
                "📤 Отправить",
                FileCB(
                    action="send", id=record_id, page=0, src="files", folder=folder_id
                ).pack(),
            ),
            _button(
                "📄 Открыть карточку",
                FileCB(
                    action="card", id=record_id, page=0, src="files", folder=folder_id
                ).pack(),
            ),
        ]
    ]
    if duplicate:
        rows.append(
            [
                _button(
                    "📂 Переместить",
                    FileCB(
                        action="move",
                        id=record_id,
                        page=0,
                        src="files",
                        folder=folder_id,
                    ).pack(),
                )
            ]
        )
    rows.append([_button("🏠 Меню", CommonCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def album_result_keyboard(folder_id: int | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    "📂 Открыть папку",
                    FolderCB(action="open", id=folder_id or 0).pack(),
                )
            ],
            [_button("🏠 Меню", CommonCB(action="main").pack())],
        ]
    )


def move_keyboard(
    file_id: int, folders: list[tuple[Folder, str]], page: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            _button(
                "🏠 Корень",
                MoveCB(action="to", file_id=file_id, folder_id=0, page=page).pack(),
            )
        ]
    )
    for folder, path in folders[:40]:
        rows.append(
            [
                _button(
                    f"📂 {truncate(path, 50)}",
                    MoveCB(
                        action="to",
                        file_id=file_id,
                        folder_id=folder.id,
                        page=page,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            _button(
                "❌ Отмена",
                MoveCB(action="cancel", file_id=file_id, page=page).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_file_keyboard(
    record_id: int, *, page: int, src: str, folder_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    "✅ Удалить",
                    FileCB(
                        action="delyes",
                        id=record_id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                ),
                _button(
                    "❌ Отмена",
                    FileCB(
                        action="delno",
                        id=record_id,
                        page=page,
                        src=src,
                        folder=folder_id,
                    ).pack(),
                ),
            ]
        ]
    )


def folders_overview_keyboard(
    own: list[Folder], shared: list[Folder]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for folder in own[:30]:
        rows.append(
            [
                _button(
                    f"📂 {truncate(folder.name, 40)}",
                    FolderCB(action="open", id=folder.id).pack(),
                )
            ]
        )
    for folder in shared[:30]:
        rows.append(
            [
                _button(
                    f"👥 {truncate(folder.name, 40)}",
                    FolderCB(action="open", id=folder.id).pack(),
                )
            ]
        )
    rows.append([_button("➕ Новая папка", FolderCB(action="new", id=0).pack())])
    rows.append([_button("🏠 Меню", CommonCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_folder_keyboard(folder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    "📤 Файлы наверх",
                    FolderCB(action="del_move", id=folder_id).pack(),
                )
            ],
            [
                _button(
                    "🗑 Удалить всё",
                    FolderCB(action="del_cascade", id=folder_id).pack(),
                )
            ],
            [
                _button(
                    "❌ Отмена",
                    FolderCB(action="open", id=folder_id).pack(),
                )
            ],
        ]
    )


def share_keyboard(
    folder_id: int, entries: list[tuple[FolderShare, User]]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for share, user in entries[:20]:
        mode = "✏️" if share.can_write else "👁"
        name = truncate(user.full_name or f"ID {user.tg_id}", 24)
        rows.append(
            [
                _button(
                    f"{mode} {name}",
                    ShareCB(
                        action="toggle",
                        folder_id=folder_id,
                        user_id=user.id,
                    ).pack(),
                ),
                _button(
                    "❌",
                    ShareCB(
                        action="remove",
                        folder_id=folder_id,
                        user_id=user.id,
                    ).pack(),
                ),
            ]
        )
    rows.append(
        [
            _button(
                "➕ Добавить пользователя",
                ShareCB(action="add", folder_id=folder_id).pack(),
            )
        ]
    )
    rows.append(
        [
            _button(
                "⬅️ К папке", FolderCB(action="open", id=folder_id).pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upload_picker_keyboard(
    folders: list[tuple[Folder, str]], current_folder_id: int | None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for folder, path in folders[:40]:
        mark = "✅ " if current_folder_id == folder.id else ""
        rows.append(
            [
                _button(
                    f"{mark}📂 {truncate(path, 50)}",
                    UploadCB(action="set", folder_id=folder.id).pack(),
                )
            ]
        )
    mark = "✅ " if current_folder_id is None else ""
    rows.append(
        [_button(f"{mark}🏠 Корень", UploadCB(action="set", folder_id=0).pack())]
    )
    rows.append([_button("🏠 Меню", CommonCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upload_hint_keyboard(folder_id: int | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("📂 Выбрать папку", UploadCB(action="pick", folder_id=0).pack()),
                _button("✅ Готово", UploadCB(action="done", folder_id=0).pack()),
            ],
            [
                _button(
                    "⬅️ К папке",
                    FolderCB(action="open", id=folder_id or 0).pack(),
                )
                if folder_id
                else _button("🏠 Меню", CommonCB(action="main").pack())
            ],
        ]
    )


def settings_keyboard(*, is_admin: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if is_admin:
        rows.append(
            [_button("👑 Админ-панель", AdminCB(action="panel").pack())]
        )
    rows.append([_button("🏠 Меню", CommonCB(action="main").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("👥 Пользователи", AdminCB(action="users").pack())],
            [_button("📊 Общая статистика", AdminCB(action="stats").pack())],
            [_button("🏠 Меню", CommonCB(action="main").pack())],
        ]
    )


def admin_users_keyboard(
    rows_data: list[tuple[User, int, int]], page: int, pages: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user, files, _size in rows_data:
        status = "✅" if user.is_active else "🚫"
        role = "👑 " if user.is_admin else ""
        username = f" @{user.username}" if user.username else ""
        rows.append(
            [
                _button(
                    f"{status} {role}{truncate(user.full_name, 18)}{username} · {files}",
                    AdminCB(action="user", page=page, user_id=user.id).pack(),
                )
            ]
        )
    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                _button("⬅️", AdminCB(action="users", page=page - 1).pack())
            )
        nav.append(_button(f"{page + 1}/{pages}", CommonCB(action="noop").pack()))
        if page + 1 < pages:
            nav.append(
                _button("➡️", AdminCB(action="users", page=page + 1).pack())
            )
        rows.append(nav)
    rows.append(
        [_button("➕ Добавить пользователя", AdminCB(action="add").pack())]
    )
    rows.append([_button("⬅️ Назад", AdminCB(action="panel").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_card_keyboard(target: User, page: int) -> InlineKeyboardMarkup:
    if target.is_active:
        action_row = [
            _button(
                "🚫 Заблокировать",
                AdminCB(action="block", page=page, user_id=target.id).pack(),
            )
        ]
    else:
        action_row = [
            _button(
                "✅ Разблокировать",
                AdminCB(action="unblock", page=page, user_id=target.id).pack(),
            )
        ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            action_row,
            [
                _button(
                    "⬅️ К пользователям",
                    AdminCB(action="users", page=page).pack(),
                )
            ],
        ]
    )


def cancel_keyboard(action: str, *, id: int = 0, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("❌ Отмена", CancelCB(action=action, id=id, page=page).pack())]
        ]
    )
