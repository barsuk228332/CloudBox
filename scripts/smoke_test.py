"""Офлайн smoke-тест CloudBox: сервисы и БД без Telegram.

Запуск:
    .venv/bin/python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cloudbox.database.engine import create_engine, create_session_factory, init_db
from cloudbox.database.repositories import files as files_repo
from cloudbox.database.repositories import folders as folders_repo
from cloudbox.services import access
from cloudbox.services import files as files_service
from cloudbox.services import folders as folders_service
from cloudbox.services import stats as stats_service
from cloudbox.services import users as users_service
from cloudbox.services.errors import AccessDenied, ServiceError
from cloudbox.utils.files import FilePayload


def payload(name: str, unique: str, size: int = 1024) -> FilePayload:
    return FilePayload(
        file_id=f"file_{unique}",
        file_unique_id=unique,
        name=name,
        size=size,
        mime_type="application/octet-stream",
        kind="document",
        telegram_date=None,
    )


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cloudbox-smoke-") as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine(f"sqlite+aiosqlite:///{db_path}")
        await init_db(engine)
        factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

        try:
            async with factory() as session:
                admin = await users_service.add_user(session, 100, full_name="Админ")
                other = await users_service.add_user(session, 200, full_name="Друг")
                stranger = await users_service.add_user(session, 300, full_name="Чужой")
                await session.commit()

                admin_user = admin.user
                admin_user.is_admin = True
                other_user = other.user
                stranger_user = stranger.user

                # --- Папки и вложенность ---
                root = await folders_service.create_folder(session, admin_user, None, "Документы")
                sub = await folders_service.create_folder(session, admin_user, root.id, "2026")
                try:
                    await folders_service.create_folder(session, admin_user, root.id, "2026")
                    raise AssertionError("Дубликат папки не был отклонён")
                except ServiceError:
                    pass

                path = await access.folder_path(session, sub.id)
                assert [f.name for f in path] == ["Документы", "2026"], path

                # --- Права ---
                assert await access.get_folder_access(session, other_user, root.id) is None
                await folders_service.add_share(session, admin_user, root.id, other_user.tg_id)
                shared_access = await access.get_folder_access(session, other_user, sub.id)
                assert shared_access is not None and shared_access.can_read
                assert not shared_access.can_write

                try:
                    await folders_service.create_folder(session, other_user, root.id, "Нельзя")
                    raise AssertionError("Получатель доступа создал подпапку")
                except AccessDenied:
                    pass

                await folders_service.set_share_write(
                    session, admin_user, root.id, other_user.id, True
                )
                shared_access = await access.get_folder_access(session, other_user, sub.id)
                assert shared_access is not None and shared_access.can_write

                # --- Загрузка и дубликаты ---
                first = await files_service.save_upload(
                    session,
                    admin_user,
                    payload("Отчёт.pdf", "uniq-1", 2048),
                    folder_id=root.id,
                    max_size_bytes=10 * 1024 * 1024,
                )
                duplicate = await files_service.save_upload(
                    session,
                    admin_user,
                    payload("Отчёт копия.pdf", "uniq-1", 2048),
                    folder_id=sub.id,
                    max_size_bytes=10 * 1024 * 1024,
                )
                assert not first.duplicate and duplicate.duplicate
                assert duplicate.record.id == first.record.id

                # Файл, загруженный другом в общую папку
                by_other = await files_service.save_upload(
                    session,
                    other_user,
                    payload("Чужой файл.txt", "uniq-2", 512),
                    folder_id=sub.id,
                    max_size_bytes=10 * 1024 * 1024,
                )
                assert by_other.record.owner_id == other_user.id

                # --- Чтение и поиск ---
                readable = await access.require_read_file(session, other_user, first.record.id)
                assert readable.id == first.record.id

                records, total = await files_service.search_files(
                    session, admin_user, "отчёт", offset=0, limit=10
                )
                assert total == 1 and records[0].id == first.record.id

                records, total = await files_service.search_files(
                    session, other_user, "чужой", offset=0, limit=10
                )
                assert total == 1 and records[0].id == by_other.record.id

                # --- Избранное ---
                assert await files_service.toggle_favorite(session, other_user, first.record.id)
                favorites, fav_total = await files_service.favorites_page(
                    session, other_user, offset=0, limit=10
                )
                assert fav_total == 1 and favorites[0].id == first.record.id
                await files_service.toggle_favorite(session, other_user, first.record.id)

                # --- Переименование и перемещение ---
                await files_service.rename_file(
                    session, admin_user, first.record.id, "Годовой отчёт.pdf"
                )
                moved = await files_service.move_file(
                    session, admin_user, first.record.id, sub.id
                )
                assert moved.folder_id == sub.id

                # --- Удаление чужого файла владельцем папки ---
                _, as_folder_owner = await files_service.get_for_delete(
                    session, admin_user, by_other.record.id
                )
                assert as_folder_owner
                try:
                    await access.require_deletable_file(
                        session, stranger_user, by_other.record.id
                    )
                    raise AssertionError("Посторонний получил право удаления")
                except AccessDenied:
                    pass

                # --- Статистика ---
                personal = await stats_service.personal(session, admin_user)
                assert personal.files == 1
                assert personal.folders == 2
                global_stats = await stats_service.global_(session)
                assert global_stats.users == 3

                # --- Удаление папки с переносом файлов ---
                await files_service.save_upload(
                    session,
                    admin_user,
                    payload("Вложенный.txt", "uniq-3", 100),
                    folder_id=sub.id,
                    max_size_bytes=10 * 1024 * 1024,
                )
                result = await folders_service.delete_folder(
                    session, admin_user, sub.id, "move"
                )
                assert result.parent_id == root.id
                assert result.files_affected == 3
                assert await folders_repo.get(session, sub.id) is None
                _root_files, root_total, _ = await files_service.folder_page(
                    session, admin_user, root.id, offset=0, limit=10
                )
                assert root_total == 3, root_total

                # --- Каскадное удаление ---
                trash = await folders_service.create_folder(session, admin_user, None, "Мусор")
                trash_file = await files_service.save_upload(
                    session,
                    admin_user,
                    payload("Удалить.txt", "uniq-4", 100),
                    folder_id=trash.id,
                    max_size_bytes=10 * 1024 * 1024,
                )
                cascade = await folders_service.delete_folder(
                    session, admin_user, trash.id, "cascade"
                )
                assert cascade.files_affected == 1
                assert await files_repo.get(session, trash_file.record.id) is None

                # --- Блокировка пользователя ---
                await users_service.block_user(session, admin_user, stranger_user)
                assert not stranger_user.is_active
                await users_service.unblock_user(session, admin_user, stranger_user)

                # --- Удаление записи владельцем и каскад избранного ---
                assert await files_service.toggle_favorite(
                    session, other_user, first.record.id
                )

                # --- Проверка доступа к файлу после отзыва share ---
                await folders_service.remove_share(
                    session, admin_user, root.id, other_user.id
                )
                assert await access.get_folder_access(session, other_user, root.id) is None
                try:
                    await access.require_read_file(
                        session, other_user, first.record.id
                    )
                    raise AssertionError("Доступ к файлу сохранился после отзыва")
                except AccessDenied:
                    pass

                await files_service.delete_file(session, admin_user, first.record.id)
                assert not await files_repo.is_favorite(
                    session, other_user.id, first.record.id
                )

                await session.commit()

            print("SMOKE_OK: папки, доступы, загрузка, поиск, избранное, статистика")
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
