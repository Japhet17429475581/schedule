from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from src.database import UserRepository
from src.handlers.schedule import schedule_service
from src.services.deepseek import DeepSeekService
from src.services.schedule import NOT_AVAILABLE_TEXT, PORTAL_DOWN_TEXT, ScheduleNotAvailableError
from src.utils import weekday_ru
from src.utils.dates import local_today

router = Router()
logger = logging.getLogger(__name__)

repo = UserRepository()
deepseek = DeepSeekService()

MIN_QUERY_LENGTH = 4


# Очевидные запросы не гоняем через DeepSeek.
_DIRECT_DAYS = {
    "вчера": "yesterday",
    "сегодня": "today",
    "завтра": "tomorrow",
}

_DIRECT_WEEKS = {
    "эта неделя": "this_week",
    "текущая неделя": "this_week",
    "на этой неделе": "this_week",
    "следующая неделя": "next_week",
    "на следующей неделе": "next_week",
}


def _direct_day(query: str) -> str | None:
    normalized = " ".join(query.lower().split())

    if normalized in _DIRECT_DAYS:
        return _DIRECT_DAYS[normalized]

    return None


def _direct_week(query: str) -> str | None:
    normalized = " ".join(query.lower().split())

    if normalized in _DIRECT_WEEKS:
        return _DIRECT_WEEKS[normalized]

    return None


def _target_date(day: str) -> date:
    today = local_today()

    offsets = {
        "yesterday": -1,
        "today": 0,
        "tomorrow": 1,
    }

    return today + timedelta(days=offsets[day])


def _week_target(week: str) -> date:
    today = local_today()

    if week == "this_week":
        return today

    if week == "next_week":
        return today + timedelta(days=7)

    raise ValueError(f"Unknown week: {week}")


def _result(
    title: str,
    text: str,
    description: str = "",
) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id="schedule",
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=text,
            parse_mode="HTML",
        ),
    )


def _help_result() -> InlineQueryResultArticle:
    return _result(
        "📅 Найти расписание",
        "📅 <b>Расписание через inline</b>\n\n"
        "Напиши в любом чате:\n"
        "👉 <code>@vgspu_schedule_bot скинь расписание на завтра</code>\n\n"
        "Например:\n"
        " • расписание на завтра\n"
        " • расписание на понедельник\n"
        " • что по парам на сегодня\n"
        " • расписание на эту неделю\n"
        " • расписание на следующую неделю\n\n"
        "Можно писать обычным языком — бот поймёт 😉",
        "Можно писать обычным языком",
    )


def _error_result(text: str) -> InlineQueryResultArticle:
    return _result(
        "⚠️ Не удалось выполнить запрос",
        text,
    )


@router.inline_query()
async def inline_schedule(query: InlineQuery) -> None:
    text = (query.query or "").strip()

    if len(text) < MIN_QUERY_LENGTH:
        await query.answer(
            [_help_result()],
            cache_time=5,
            is_personal=True,
        )
        return

    group = await repo.get_group(query.from_user.id)

    if not group:
        await query.answer(
            [
                _error_result(
                    "⚠️ <b>Сначала выбери группу</b> в боте через /start, "
                    "а затем используй inline-режим."
                )
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    try:
        # ============================================================
        # НЕДЕЛИ
        # ============================================================

        week = _direct_week(text)

        if week is not None:
            target = _week_target(week)

            lessons = await schedule_service.week(
                group,
                target=target,
            )

            rendered = schedule_service.render_week(
                group,
                lessons,
                target=target,
            )

            if week == "this_week":
                title = "🗓 Эта неделя"
                description = f"Группа: {group}"
            else:
                title = "🗓 Следующая неделя"
                description = f"Группа: {group}"

            await query.answer(
                [
                    _result(
                        title,
                        rendered,
                        description,
                    )
                ],
                cache_time=30,
                is_personal=True,
            )
            await repo.track_outcome(query.from_user.id, "schedule_success", "inline:week")
            return

        # ============================================================
        # ДНИ
        # ============================================================

        day = _direct_day(text)

        if day is None:
            parsed = await deepseek.parse(text)

            if parsed["intent"] != "schedule" or parsed["date"] == "unknown":
                await query.answer(
                    [
                        _error_result(
                            "Не понял запрос. Попроси расписание на "
                            "<b>вчера, сегодня, завтра, эту или "
                            "следующую неделю</b>."
                        )
                    ],
                    cache_time=5,
                    is_personal=True,
                )
                return

            day = parsed["date"]

        if day in {"this_week", "next_week"}:
            target = _week_target(day)
            lessons = await schedule_service.week(group, target)
            rendered = schedule_service.render_week(group, lessons, target)
            await query.answer(
                [_result("🗓 Расписание недели", rendered, f"Группа: {group}")],
                cache_time=30,
                is_personal=True,
            )
            await repo.track_outcome(query.from_user.id, "schedule_success", "inline:week")
            return

        target = _target_date(day)

        # Жёсткое ограничение:
        # обычный inline-режим для дней работает только
        # в диапазоне вчера / сегодня / завтра.
        today = _target_date("today")

        if target < today - timedelta(days=1) or target > today + timedelta(days=1):
            await query.answer(
                [_error_result("Можно запросить только вчера, сегодня или завтра.")],
                cache_time=30,
                is_personal=True,
            )
            return

        lessons = await schedule_service.day(
            group,
            target,
        )

        rendered = schedule_service.render_day(
            group,
            target,
            lessons,
        )

        await query.answer(
            [
                _result(
                    f"📅 {weekday_ru(target)}, {target:%d.%m}",
                    rendered,
                    f"Группа: {group}",
                )
            ],
            cache_time=30,
            is_personal=True,
        )
        await repo.track_outcome(query.from_user.id, "schedule_success", "inline:day")

    except ScheduleNotAvailableError:
        await repo.track_outcome(query.from_user.id, "schedule_unavailable", "inline")
        await query.answer([_error_result(NOT_AVAILABLE_TEXT)], cache_time=1, is_personal=True)
    except httpx.HTTPError:
        await repo.track_outcome(query.from_user.id, "schedule_error", "inline")
        await query.answer([_error_result(PORTAL_DOWN_TEXT)], cache_time=5, is_personal=True)
    except Exception:
        await repo.track_outcome(query.from_user.id, "schedule_error", "inline")
        logger.exception(
            "Inline schedule error for user %s",
            query.from_user.id,
        )

        await query.answer(
            [_error_result("⚠️ Не удалось получить расписание. Попробуй ещё раз.")],
            cache_time=5,
            is_personal=True,
        )
