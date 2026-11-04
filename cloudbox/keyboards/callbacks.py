from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FileCB(CallbackData, prefix="f"):
    action: str
    id: int
    page: int = 0
    src: str = "files"
    folder: int = 0


class NavCB(CallbackData, prefix="n"):
    scope: str
    page: int = 0
    folder: int = 0


class FolderCB(CallbackData, prefix="d"):
    action: str
    id: int
    page: int = 0


class ShareCB(CallbackData, prefix="s"):
    action: str
    folder_id: int
    user_id: int = 0


class MoveCB(CallbackData, prefix="m"):
    action: str
    file_id: int
    folder_id: int = 0
    page: int = 0


class UploadCB(CallbackData, prefix="u"):
    action: str
    folder_id: int = 0


class AdminCB(CallbackData, prefix="a"):
    action: str
    page: int = 0
    user_id: int = 0


class CommonCB(CallbackData, prefix="c"):
    action: str


class CancelCB(CallbackData, prefix="x"):
    action: str
    id: int = 0
    page: int = 0
