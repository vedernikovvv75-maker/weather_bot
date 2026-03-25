from aiogram.fsm.state import State, StatesGroup


class AddStates(StatesGroup):
    # Ждём текст задачи после команды /add.
    waiting_text = State()

