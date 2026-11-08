from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.database import UserRepository
from src.keyboards import schedule_nav_menu, settings_menu
from src.services.schedule import (
    NOT_AVAILABLE_TEXT,
    PORTAL_DOWN_TEXT,
    ScheduleNotAvailableError,
    ScheduleService,
)
from src.states import ScreenState
from src.utils import esc
from src.utils.dates import local_today

router = Router()
repo = UserRepository()
schedule_service = ScheduleService()
logger = logging.getLogger(__name__)


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
) -> bool:
    """
    Безопасное редактирование сообщения.

    Возвращает True, если сообщение изменено,
    False, если Telegram отказал в редактировании.
    """
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
        )
        return True

    except TelegramBadRequest as e:
        error = str(e).lower()

        # Сообщение уже содержит такой же текст/клавиатуру.
        if "message is not modified" in error:
            return False

        # Сообщение нельзя изменить (например, оно уже удалено
        # или является неподходящим типом сообщения).
        if (
            "message to edit not found" in error
            or "message can't be edited" in error
            or "message cannot be edited" in error
        ):
            return False

        raise


async def render_for_user(
    callback: CallbackQuery,
    kind: str,
    force_refresh: bool = False,
) -> None:
    group = await repo.get_group(callback.from_user.id)

    if not group:
        await safe_edit(
            callback,
            "⚠️ Сначала укажи учебную группу через /start.",
        )
        return

    today = local_today()

    if kind == "today":
        target = today

        lessons = await schedule_service.day(
            group,
            target,
            force_refresh=force_refresh,
        )

        text = schedule_service.render_day(
            group,
            target,
            lessons,
        )

    elif kind == "tomorrow":
        target = today + timedelta(days=1)

        lessons = await schedule_service.day(
            group,
            target,
            force_refresh=force_refresh,
        )

        text = schedule_service.render_day(
            group,
            target,
            lessons,
        )

    elif kind.startswith("week"):
        offset = int(kind.split(":", 1)[1]) if ":" in kind else 0

        target = today + timedelta(days=7 * offset)

        lessons = await schedule_service.week(
            group,
            target,
            force_refresh=force_refresh,
        )

        text = schedule_service.render_week(
            group,
            lessons,
            target,
        )

    else:
        raise ValueError(f"Неизвестный экран расписания: {kind}")

    await safe_edit(
        callback,
        text,
        reply_markup=schedule_nav_menu(kind),
    )
    await repo.track_outcome(callback.from_user.id, "schedule_success", kind)


async def show_schedule_error(callback: CallbackQuery, kind: str, exc: Exception) -> None:
    if isinstance(exc, ScheduleNotAvailableError):
        text, outcome = NOT_AVAILABLE_TEXT, "schedule_unavailable"
    elif isinstance(exc, httpx.HTTPError):
        text, outcome = PORTAL_DOWN_TEXT, "schedule_error"
    else:
        logger.error("Schedule request failed", exc_info=(type(exc), exc, exc.__traceback__))
        text, outcome = "⚠️ Не удалось получить расписание. Попробуй позже.", "schedule_error"
    await repo.track_outcome(callback.from_user.id, outcome, kind)
    await safe_edit(callback, text, reply_markup=schedule_nav_menu(kind))


@router.callback_query(
    F.data.in_(
        {
            "schedule:today",
            "schedule:tomorrow",
            "schedule:week:0",
            "schedule:week:1",
        }
    )
)
async def schedule_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer()

    kind = callback.data.split(":", 1)[1]

    await state.set_state(ScreenState.viewing_schedule)

    await state.update_data(schedule_kind=kind)

    try:
        await render_for_user(
            callback,
            kind,
        )

    except Exception as exc:
        await show_schedule_error(callback, kind, exc)


@router.callback_query(F.data == "schedule:refresh_menu")
async def refresh_menu(
    callback: CallbackQuery,
):
    await callback.answer("Кэш очищен")

    group = await repo.get_group(callback.from_user.id)

    if group:
        schedule_service.invalidate(group)

    await safe_edit(
        callback,
        f"⚙️ <b>Настройки</b>\n\n"
        f"Группа: <b>{esc(group) if group else 'не указана'}</b>\n\n"
        f"Выбери действие:",
        reply_markup=settings_menu(),
    )


@router.callback_query(F.data.startswith("schedule:refresh:"))
async def refresh_current(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer("Обновляю расписание…")

    kind = callback.data.removeprefix("schedule:refresh:")

    group = await repo.get_group(callback.from_user.id)

    if not group:
        await safe_edit(
            callback,
            "⚠️ Сначала укажи группу через /start.",
        )
        return

    # Полностью очищаем кэш группы.
    schedule_service.invalidate(group)

    try:
        await render_for_user(
            callback,
            kind,
            force_refresh=True,
        )

        await state.set_state(ScreenState.viewing_schedule)

        await state.update_data(schedule_kind=kind)

    except Exception as exc:
        # Если проблема не в Telegram edit_text,
        # показываем пользователю нормальное сообщение.
        await show_schedule_error(callback, kind, exc)
