from aiogram.fsm.state import State, StatesGroup


class RenameFile(StatesGroup):
    waiting = State()


class RenameFolder(StatesGroup):
    waiting = State()


class CreateFolder(StatesGroup):
    waiting = State()


class ShareAdd(StatesGroup):
    waiting = State()


class SearchForm(StatesGroup):
    waiting = State()
    results = State()


class AdminAddUser(StatesGroup):
    waiting = State()
