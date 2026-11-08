from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from src.config import settings
from src.database import UserRepository
from src.parsers import Lesson, ScheduleParser
from src.parsers.vspu import ScheduleNotFoundError
from src.utils import esc, week_bounds, weekday_ru
from src.utils.dates import local_today

logger = logging.getLogger(__name__)

NOT_AVAILABLE_TEXT = (
    "📭 <b>К сожалению, на портале ВГСПУ нет расписания твоей группы "
    "на выбранную неделю.</b>\n\n"
    "Возможно, оно появится позже. Попробуй проверить расписание позднее "
    "или выбери другую неделю."
)
PORTAL_DOWN_TEXT = "⚠️ Портал ВГСПУ сейчас недоступен. Попробуй через несколько минут."


TYPE_LABELS = {
    "lecture": "🎓 Лекция",
    "practice": "🛠️ Практика",
    "lab": "🧪 Лабораторная",
    "seminar": "💬 Семинар",
    "consultation": "👨‍🏫 Консультация",
    "exam": "📝 Экзамен",
    "credit": "✅ Зачёт",
}


class ScheduleNotAvailableError(ValueError):
    """Портал ответил, но расписание группы на выбранную неделю отсутствует."""


@dataclass(slots=True)
class CacheEntry:
    created_at: datetime
    lessons: list[Lesson]


class ScheduleService:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int], CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._parser = ScheduleParser()
        self._repo = UserRepository()

    async def get_schedule(
        self,
        group: str,
        target: date | None = None,
        force_refresh: bool = False,
    ) -> list[Lesson]:
        group = group.strip()
        if not group:
            raise ValueError("Группа не указана")
        target = target or local_today()

        iso = target.isocalendar()
        cache_key = (group, iso.year, iso.week)

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached and (datetime.now() - cached.created_at).total_seconds() < settings.cache_ttl:
                return cached.lessons

        async with self._lock:
            if not force_refresh:
                cached = self._cache.get(cache_key)
                if (
                    cached
                    and (datetime.now() - cached.created_at).total_seconds() < settings.cache_ttl
                ):
                    return cached.lessons

            try:
                content = await self._fetch_html(group, iso.week, iso.year)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise ScheduleNotAvailableError("Schedule page not found") from exc
                raise

            try:
                lessons = self._parser.parse(content)
            except ScheduleNotFoundError as exc:
                # Ничего не кэшируем: когда неделю опубликуют,
                # следующий запрос сразу получит актуальные данные.
                raise ScheduleNotAvailableError(str(exc)) from exc

            self._cache[cache_key] = CacheEntry(datetime.now(), lessons)
            if len(self._cache) > 256:
                oldest = min(self._cache, key=lambda key: self._cache[key].created_at)
                self._cache.pop(oldest, None)

            # Кэш вчерашнего дня сохраняется в БД и переживает рестарты.
            try:
                await self._repo.save_schedule_cache(group, lessons)
            except Exception:
                logger.exception("Could not persist schedule cache for %s", group)
            return lessons

    async def validate_group(self, group: str) -> bool:
        """Проверяет группу даже в неделю без занятий.

        Пустое расписание не означает, что группы не существует: в выходные,
        каникулы или при отменах портал может вернуть пустую неделю. Поэтому
        пробуем несколько соседних недель и считаем группу валидной, если хотя
        бы одна из них успешно распарсилась.
        """
        group = group.strip()
        if not group:
            return False

        today = local_today()
        # Сначала текущая неделя, затем будущие и прошлая. Это важно для
        # воскресенья/выходных и недель, где все пары отменены.
        for offset in (0, 7, 14, -7):
            try:
                await self.get_schedule(
                    group,
                    target=today + timedelta(days=offset),
                    force_refresh=True,
                )
                return True
            except ScheduleNotAvailableError:
                continue

        return False

    def invalidate(self, group: str | None = None) -> None:
        if group is None:
            self._cache.clear()
        else:
            for key in list(self._cache):
                if key[0] == group.strip():
                    self._cache.pop(key, None)

    async def _fetch_html(
        self, group: str, week: int | None = None, year: int | None = None
    ) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
        }
        timeout = httpx.Timeout(settings.request_timeout)
        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as client:
            params = {"group": group}
            if week is not None and year is not None:
                params["week"] = week
                params["year"] = year
            response = await client.get(settings.portal_url, params=params)
            response.raise_for_status()
            return response.text

    async def day(self, group: str, target: date, force_refresh: bool = False) -> list[Lesson]:
        if target < local_today() and not force_refresh:
            try:
                cached_day = await self._repo.get_schedule_cache(group, target)
                if cached_day:
                    return self._cache_rows_to_lessons(cached_day)
            except Exception:
                logger.exception("Could not read schedule cache for %s", group)
        lessons = await self.get_schedule(group, target=target, force_refresh=force_refresh)
        return [lesson for lesson in lessons if lesson.date == target]

    async def week(
        self, group: str, target: date | None = None, force_refresh: bool = False
    ) -> list[Lesson]:
        lessons = await self.get_schedule(group, target=target, force_refresh=force_refresh)
        start, end = week_bounds(target)
        return [lesson for lesson in lessons if start <= lesson.date <= end]

    @staticmethod
    def _cache_rows_to_lessons(rows: list) -> list[Lesson]:
        return [
            Lesson(
                date=row.lesson_date,
                start=row.lesson_start,
                end=row.lesson_end,
                subject=row.subject,
                lesson_type=row.lesson_type,
                teacher=row.teacher or "",
                room=row.room or "",
            )
            for row in rows
        ]

    @staticmethod
    def render_day(group: str, target: date, lessons: list[Lesson]) -> str:
        title = f"📅 <b>{weekday_ru(target)}, {target:%d.%m}</b>"
        lines = [title, f"Группа: <b>{esc(group)}</b>", ""]
        if not lessons:
            lines.append("Пар нет. Можно отдыхать 😎")
            return "\n".join(lines)
        for index, lesson in enumerate(lessons, 1):
            type_label = TYPE_LABELS.get(lesson.lesson_type)
            suffix = f" · {type_label}" if type_label else ""
            lines.append(f"<b>{index}. 🕐 {lesson.start}–{lesson.end}</b>{suffix}")
            lines.append(f"📘 {esc(lesson.subject)}")
            if lesson.teacher:
                lines.append(f"👨‍🏫 {esc(lesson.teacher)}")
            if lesson.room:
                lines.append(f"🚪 <code>{esc(lesson.room)}</code>")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def render_week(group: str, lessons: list[Lesson], target: date | None = None) -> str:
        start, _ = week_bounds(target)
        lines = [
            f"🗓 <b>Неделя {start:%d.%m} — {(start + timedelta(days=6)):%d.%m}</b>",
            f"Группа: <b>{esc(group)}</b>",
            "",
        ]
        by_day = {day: [] for day in (start + timedelta(days=i) for i in range(7))}
        for lesson in lessons:
            by_day.setdefault(lesson.date, []).append(lesson)
        for day, day_lessons in by_day.items():
            lines.append(f"<b>{weekday_ru(day)}, {day:%d.%m}</b>")
            if not day_lessons:
                lines.append("— пар нет —")
            else:
                for index, lesson in enumerate(day_lessons, 1):
                    type_label = TYPE_LABELS.get(lesson.lesson_type)
                    suffix = f" · {type_label}" if type_label else ""
                    lines.append(f"{index}. 🕐 <b>{lesson.start}–{lesson.end}</b>{suffix}")
                    lines.append(f"   📘 {esc(lesson.subject)}")
                    if lesson.teacher:
                        lines.append(f"   👨‍🏫 {esc(lesson.teacher)}")
                    if lesson.room:
                        lines.append(f"   🚪 <code>{esc(lesson.room)}</code>")
            lines.append("")
        return "\n".join(lines).strip()
