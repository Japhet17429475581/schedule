from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from src.database import UserRepository
from src.keyboards import main_menu

user_repo = UserRepository()


async def get_user_group(telegram_id: int) -> str | None:
    return await user_repo.get_group(telegram_id)


async def show_menu(target: Message | CallbackQuery, group: str) -> None:
    text = f"👋 <b>Расписание ВГСПУ</b>\n\nТвоя группа: <b>{group}</b>\n\nВыбери, что показать:"
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=main_menu())
    else:
        await target.answer(text, reply_markup=main_menu())
