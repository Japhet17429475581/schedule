from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from src.database import UserRepository
from src.handlers.schedule import schedule_service
from src.keyboards import quick_menu
from src.services.schedule import NOT_AVAILABLE_TEXT, PORTAL_DOWN_TEXT, ScheduleNotAvailableError
from src.states import ScreenState
from src.utils.dates import local_today

router = Router()
repo = UserRepository()
logger = logging.getLogger(__name__)


async def send_schedule(message: Message, kind: str) -> None:
    group = await repo.get_group(message.from_user.id)
    if not group:
        await message.answer("⚠️ Сначала укажи группу через /start.", reply_markup=quick_menu())
        return
    target = local_today() + timedelta(
        days={"today": 0, "tomorrow": 1, "week": 0, "next_week": 7}[kind]
    )
    outcome = "schedule_success"
    try:
        if kind in {"week", "next_week"}:
            lessons = await schedule_service.week(group, target)
            text = schedule_service.render_week(group, lessons, target)
        else:
            lessons = await schedule_service.day(group, target)
            text = schedule_service.render_day(group, target, lessons)
    except ScheduleNotAvailableError:
        outcome, text = "schedule_unavailable", NOT_AVAILABLE_TEXT
    except httpx.HTTPError:
        outcome, text = "schedule_error", PORTAL_DOWN_TEXT
    except Exception:
        logger.exception("Quick schedule failed")
        outcome, text = "schedule_error", "⚠️ Не удалось получить расписание. Попробуй позже."
    await repo.track_outcome(message.from_user.id, outcome, kind)
    await message.answer(text, reply_markup=quick_menu())


@router.message(StateFilter(None, ScreenState.viewing_schedule), F.text == "📅 Сегодня")
async def quick_today(message: Message):
    await send_schedule(message, "today")


@router.message(StateFilter(None, ScreenState.viewing_schedule), F.text == "📆 Завтра")
async def quick_tomorrow(message: Message):
    await send_schedule(message, "tomorrow")


@router.message(StateFilter(None, ScreenState.viewing_schedule), F.text == "🗓 Неделя")
async def quick_week(message: Message):
    await send_schedule(message, "week")


@router.message(StateFilter(None, ScreenState.viewing_schedule), F.text == "➡️ Следующая неделя")
async def quick_next_week(message: Message):
    await send_schedule(message, "next_week")
