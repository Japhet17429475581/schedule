from aiogram.fsm.state import State, StatesGroup


class GroupState(StatesGroup):
    waiting_for_group = State()
