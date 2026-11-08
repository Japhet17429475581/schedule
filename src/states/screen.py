from aiogram.fsm.state import State, StatesGroup


class ScreenState(StatesGroup):
    viewing_schedule = State()
