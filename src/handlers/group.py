from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.database import UserRepository
from src.handlers.schedule import schedule_service
from src.keyboards import cancel_group_menu, main_menu, quick_menu
from src.services.groups import is_valid_group_format, normalize_group
from src.services.schedule import NOT_AVAILABLE_TEXT, PORTAL_DOWN_TEXT
from src.states import GroupState

router = Router()
repo = UserRepository()


async def ask_group(message: Message, state: FSMContext, edit: bool = False) -> None:
    await state.set_state(GroupState.waiting_for_group)
    text = (
        "⚙️ <b>Смена группы</b>\n\n"
        "Введи новую учебную группу.\n\n"
        "Формат: <code>АВБ-111</code>\n"
        "Например: <code>ИЯ-АВБ-111</code>"
    )
    if edit:
        await message.edit_text(text)
        await message.answer("Нажми ❌ Отмена, если передумал.", reply_markup=cancel_group_menu())
    else:
        await message.answer(text, reply_markup=cancel_group_menu())


@router.message(F.text == "🔄 Сменить группу")
async def quick_change_group(message: Message, state: FSMContext):
    await ask_group(message, state, edit=False)


@router.callback_query(F.data == "group:change")
async def change_group(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_group(callback.message, state, edit=True)


@router.message(GroupState.waiting_for_group, F.text == "❌ Отмена")
async def cancel_group_change(message: Message, state: FSMContext):
    await state.clear()
    group = await repo.get_group(message.from_user.id)
    if group:
        await message.answer(
            f"↩️ <b>Смена группы отменена.</b>\n\nТвоя группа: <b>{group}</b>",
            reply_markup=quick_menu(),
        )
    else:
        await message.answer(
            "↩️ Смена отменена.",
            reply_markup=quick_menu(),
        )


@router.message(GroupState.waiting_for_group)
async def group_input(message: Message, state: FSMContext):
    group = normalize_group(message.text or "")
    if not is_valid_group_format(group):
        await message.answer(
            "⚠️ <b>Неверный формат группы.</b>\n\n"
            "Введи код без пробелов. Например: <code>ИЯ-АВБ-111</code>"
        )
        return

    checking = await message.answer("⏳ Проверяю группу на портале ВГСПУ...")
    try:
        available = await schedule_service.validate_group(group)
    except httpx.HTTPError:
        await checking.edit_text(PORTAL_DOWN_TEXT)
        return
    if not available:
        await checking.edit_text(NOT_AVAILABLE_TEXT + "\n\nПроверь код группы или введи его позже.")
        await repo.track_outcome(message.from_user.id, "group_unavailable", group)
        return

    await repo.set_group(message.from_user.id, group)
    await state.clear()
    await checking.edit_text(
        f"✅ <b>Группа сохранена!</b>\n\nТвоя группа: <b>{group}</b>\n\nВыбирай расписание:",
        reply_markup=main_menu(),
    )
    await message.answer("⚡ Быстрые действия доступны снизу.", reply_markup=quick_menu())
