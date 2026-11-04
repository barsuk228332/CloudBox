from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_FILES = "📁 Мои файлы"
BTN_FOLDERS = "📂 Мои папки"
BTN_UPLOAD = "📤 Загрузить"
BTN_FAVORITES = "⭐ Избранное"
BTN_SEARCH = "🔍 Поиск"
BTN_STATS = "📊 Статистика"
BTN_SETTINGS = "⚙️ Настройки"

MENU_TEXTS = {
    BTN_FILES,
    BTN_FOLDERS,
    BTN_UPLOAD,
    BTN_FAVORITES,
    BTN_SEARCH,
    BTN_STATS,
    BTN_SETTINGS,
}


def main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=BTN_FILES), KeyboardButton(text=BTN_FOLDERS)],
        [KeyboardButton(text=BTN_UPLOAD), KeyboardButton(text=BTN_FAVORITES)],
        [KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_STATS)],
        [KeyboardButton(text=BTN_SETTINGS)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Отправьте файл или выберите действие",
    )
