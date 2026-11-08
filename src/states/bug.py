from aiogram.fsm.state import State, StatesGroup


class BugReportState(StatesGroup):
    waiting_for_text = State()
