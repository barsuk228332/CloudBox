from __future__ import annotations


class ServiceError(Exception):
    """Ошибка бизнес-правила, текст можно показать пользователю."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AccessDenied(ServiceError):
    def __init__(self, message: str = "У вас нет доступа к этому действию.") -> None:
        super().__init__(message)


class NotFoundError(ServiceError):
    def __init__(self, message: str = "Запись не найдена.") -> None:
        super().__init__(message)
