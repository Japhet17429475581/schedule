from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.database import UserRepository
from src.keyboards import main_menu, schedule_menu, settings_menu

router = Router()
repo = UserRepository()


@router.callback_query(F.data == "nav:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    group = await repo.get_group(callback.from_user.id)
    if not group:
        await callback.message.edit_text("⚠️ Сначала укажи группу через /start.")
        return
    await callback.message.edit_text(
        f"🎓 <b>Расписание ВГСПУ</b>\n\nТвоя группа: <b>{group}</b>\n\nВыбери нужный раздел:",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "nav:schedule")
async def nav_to_schedule(callback: CallbackQuery):
    await callback.answer()
    group = await repo.get_group(callback.from_user.id)
    if not group:
        await callback.message.edit_text("⚠️ Сначала укажи группу через /start.")
        return
    await callback.message.edit_text(
        f"📅 <b>Расписание</b>\n\nГруппа: <b>{group}</b>\n\nВыбери, что показать:",
        reply_markup=schedule_menu(),
    )


@router.callback_query(F.data == "nav:settings")
async def nav_to_settings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nВыбери, что хочешь изменить:",
        reply_markup=settings_menu(),
    )


@router.callback_query(F.data == "menu:schedule")
async def menu_schedule(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    group = await repo.get_group(callback.from_user.id)
    if not group:
        await callback.message.edit_text("⚠️ Сначала укажи группу через /start.")
        return
    await callback.message.edit_text(
        f"📅 <b>Расписание</b>\n\nГруппа: <b>{group}</b>\n\nВыбери, что показать:",
        reply_markup=schedule_menu(),
    )


@router.callback_query(F.data == "menu:settings")
async def menu_settings(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nВыбери, что хочешь изменить:",
        reply_markup=settings_menu(),
    )
