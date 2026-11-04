from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from ..keyboards.reply import main_menu

router = Router(name="fallback")


@router.message()
async def fallback_message(message: Message) -> None:
    await message.answer(
        "Не понял сообщение. Отправьте файл или воспользуйтесь меню ниже. "
        "Справка — /help.",
        reply_markup=main_menu(),
    )


@router.callback_query()
async def fallback_callback(callback: CallbackQuery) -> None:
    await callback.answer(
        "Кнопка устарела. Откройте меню заново командой /start.",
        show_alert=True,
    )
