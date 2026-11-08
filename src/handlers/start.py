from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.database import UserRepository
from src.keyboards import main_menu, quick_menu
from src.states import GroupState
from src.utils import esc

router = Router()
repo = UserRepository()

WELCOME = (
    "👋 <b>Привет, студент ВГСПУ!</b>\n\n"
    "Для начала введи свою учебную группу.\n\n"
    "Формат: <code>АВБ-111</code>\n"
    "Например: <code>ИЯ-АВБ-111</code>"
)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    group = await repo.get_group(message.from_user.id)
    if group:
        await state.clear()
        await message.answer(
            f"👋 <b>С возвращением!</b>\n\nТвоя группа: <b>{esc(group)}</b>\n\nВыбери нужный раздел:",
            reply_markup=main_menu(),
        )
        await message.answer("⚡ Быстрые действия всегда здесь:", reply_markup=quick_menu())
        return
    await state.set_state(GroupState.waiting_for_group)
    await message.answer(WELCOME)
