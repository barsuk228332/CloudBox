from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..database.models import User
from ..keyboards.inline import album_result_keyboard, upload_result_keyboard
from ..keyboards.reply import main_menu
from ..services import files as files_service
from ..services import folders as folders_service
from ..services.albums import AlbumBuffer, UploadSummary
from ..services.errors import ServiceError
from ..utils.files import SUPPORTED_CONTENT_TYPES, extract_file_payload
from ..utils.formatting import esc, human_size, kind_icon, truncate

router = Router(name="upload")


async def _folder_label(
    session: AsyncSession, folder_id: int | None
) -> str:
    if folder_id is None:
        return "Корень"
    names = await folders_service.folder_path_names(session, folder_id)
    return " / ".join(esc(name) for name in names) if names else "Корень"


async def _send_single_result(
    message: Message,
    *,
    session: AsyncSession,
    record,  # type: ignore[no-untyped-def]
    duplicate: bool,
    folder_id: int | None,
) -> None:
    label = await _folder_label(session, folder_id)
    if duplicate:
        text = (
            "ℹ️ <b>Этот файл уже есть в каталоге</b>\n\n"
            f"{kind_icon(record.kind)} <b>{esc(record.name)}</b>\n"
            f"📏 {human_size(record.size)}\n"
            f"📂 {label}\n\n"
            "Повторно сохранять не стал. Можно открыть карточку или "
            "переместить запись в другую папку."
        )
    else:
        text = (
            "✅ <b>Файл сохранён</b>\n\n"
            f"{kind_icon(record.kind)} <b>{esc(record.name)}</b>\n"
            f"📏 {human_size(record.size)}\n"
            f"📂 {label}"
        )
    await message.answer(
        text,
        reply_markup=upload_result_keyboard(
            record.id, folder_id=folder_id or 0, duplicate=duplicate
        ),
    )


async def _send_album_result(message: Message, items: list[UploadSummary]) -> None:
    total_size = sum(item.size for item in items)
    duplicates = sum(1 for item in items if item.duplicate)
    folder_label = items[0].folder_label if items else "Корень"

    lines = [
        f"✅ <b>Сохранено файлов: {len(items)}</b>",
        "",
        f"💾 Общий размер: {human_size(total_size)}",
        f"📂 Папка: {folder_label}",
    ]
    if duplicates:
        lines.append(f"ℹ️ Уже были в каталоге: {duplicates}")

    lines.append("")
    for item in items[:8]:
        lines.append(
            f"{kind_icon(item.kind)} {esc(truncate(item.name, 45))} · "
            f"{human_size(item.size)}"
        )
    if len(items) > 8:
        lines.append(f"… и ещё {len(items) - 8}")

    await message.answer(
        "\n".join(lines),
        reply_markup=album_result_keyboard(items[0].folder_id if items else None),
    )


@router.message(F.content_type.in_(SUPPORTED_CONTENT_TYPES))
async def handle_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    config: Config,
    album_buffer: AlbumBuffer,
) -> None:
    payload = extract_file_payload(message)
    if payload is None:
        await message.answer(
            "Этот тип вложения не поддерживается. Отправьте документ, фото, "
            "видео, аудио, голосовое сообщение, видеокружок или анимацию.",
            reply_markup=main_menu(),
        )
        return

    data = await state.get_data()
    folder_id = data.get("upload_folder_id")

    try:
        result = await files_service.save_upload(
            session,
            user,
            payload,
            folder_id=folder_id,
            max_size_bytes=config.max_file_size_bytes,
        )
    except ServiceError as exc:
        await message.answer(
            f"⚠️ {esc(exc.message)}", reply_markup=main_menu()
        )
        return

    folder_label = await _folder_label(session, result.folder_id)

    if message.media_group_id is not None:
        summary = UploadSummary(
            record_id=result.record.id,
            name=result.record.name,
            size=result.record.size,
            kind=result.record.kind,
            duplicate=result.duplicate,
            folder_id=result.folder_id,
            folder_label=folder_label,
        )
        key = (message.chat.id, int(message.media_group_id))

        async def flush(items: list[UploadSummary]) -> None:
            await _send_album_result(message, items)

        album_buffer.add(key, summary, flush)
        return

    await _send_single_result(
        message,
        session=session,
        record=result.record,
        duplicate=result.duplicate,
        folder_id=result.folder_id,
    )


@router.message(
    F.sticker
    | F.contact
    | F.location
    | F.venue
    | F.poll
    | F.dice
    | F.game
)
async def unsupported_message(message: Message) -> None:
    await message.answer(
        "Этот тип сообщения не поддерживается. CloudBox хранит документы, "
        "фото, видео, аудио, голосовые, видеокружки и анимации.",
        reply_markup=main_menu(),
    )
