from __future__ import annotations

import logging
from datetime import date, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.utils.dates import LOCAL_TZ, local_today, utc_now

from .models import ScheduleCache, User, UserActivity, UserDailyActivity, UserStats
from .session import SessionFactory

logger = logging.getLogger(__name__)
INTERACTION_EVENTS = {"message", "callback", "inline"}


def upsert_for(session):
    return sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert


class UserRepository:
    async def get_group(self, telegram_id: int) -> str | None:
        async with SessionFactory() as session:
            return await session.scalar(
                select(User.group_code).where(User.telegram_id == telegram_id)
            )

    async def set_group(self, telegram_id: int, group_code: str) -> None:
        async with SessionFactory() as session:
            stmt = upsert_for(session)(User).values(telegram_id=telegram_id, group_code=group_code)
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[User.telegram_id],
                    set_={"group_code": group_code, "updated_at": utc_now()},
                )
            )
            session.add(
                UserActivity(
                    telegram_id=telegram_id, event_type="group_selected", details=group_code
                )
            )
            await session.commit()

    async def count_users(self) -> int:
        async with SessionFactory() as session:
            return int(await session.scalar(select(func.count()).select_from(User)) or 0)

    async def group_stats(self) -> list[tuple[str, int]]:
        async with SessionFactory() as session:
            result = await session.execute(
                select(User.group_code, func.count())
                .where(User.group_code.is_not(None))
                .group_by(User.group_code)
                .order_by(func.count().desc())
            )
            return [(group, int(count)) for group, count in result if group]

    async def track_activity(
        self, telegram_id: int, event_type: str, details: str | None = None
    ) -> None:
        now = utc_now()
        async with SessionFactory() as session:
            session.add(
                UserActivity(
                    telegram_id=telegram_id, event_type=event_type, details=details, created_at=now
                )
            )
            if event_type in INTERACTION_EVENTS:
                insert = upsert_for(session)
                messages = int(event_type == "message")
                callbacks = int(event_type == "callback")
                stmt = insert(UserStats).values(
                    telegram_id=telegram_id,
                    first_seen_at=now,
                    last_active_at=now,
                    message_count=messages,
                    callback_count=callbacks,
                )
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[UserStats.telegram_id],
                        set_={
                            "last_active_at": now,
                            "message_count": UserStats.message_count + messages,
                            "callback_count": UserStats.callback_count + callbacks,
                        },
                    )
                )
                activity_date = now.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).date()
                stmt = insert(UserDailyActivity).values(
                    telegram_id=telegram_id,
                    activity_date=activity_date,
                    message_count=messages,
                    callback_count=callbacks,
                    inline_count=int(event_type == "inline"),
                )
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[
                            UserDailyActivity.telegram_id,
                            UserDailyActivity.activity_date,
                        ],
                        set_={
                            "message_count": UserDailyActivity.message_count + messages,
                            "callback_count": UserDailyActivity.callback_count + callbacks,
                            "inline_count": UserDailyActivity.inline_count
                            + int(event_type == "inline"),
                        },
                    )
                )
            await session.commit()

    async def track_outcome(
        self, telegram_id: int, outcome: str, details: str | None = None
    ) -> None:
        try:
            await self.track_activity(telegram_id, outcome, details)
        except Exception:
            logger.exception("Could not record outcome %s", outcome)

    async def activity_stats(self) -> dict:
        from .analytics import analytics_report

        async with SessionFactory() as session:
            return await analytics_report(session)

    async def save_schedule_cache(self, group_code: str, lessons: list) -> None:
        cutoff = local_today() - timedelta(days=1)
        async with SessionFactory() as session:
            await session.execute(
                ScheduleCache.__table__.delete().where(ScheduleCache.lesson_date < cutoff)
            )
            dates = {lesson.date for lesson in lessons if lesson.date >= cutoff}
            if dates:
                await session.execute(
                    ScheduleCache.__table__.delete().where(
                        ScheduleCache.group_code == group_code,
                        ScheduleCache.lesson_date.in_(dates),
                    )
                )
            for lesson in lessons:
                if lesson.date >= cutoff:
                    session.add(
                        ScheduleCache(
                            group_code=group_code,
                            lesson_date=lesson.date,
                            lesson_start=lesson.start,
                            lesson_end=lesson.end,
                            subject=lesson.subject,
                            lesson_type=lesson.lesson_type,
                            teacher=lesson.teacher or None,
                            room=lesson.room or None,
                        )
                    )
            await session.commit()

    async def get_schedule_cache(self, group_code: str, target: date) -> list[ScheduleCache]:
        async with SessionFactory() as session:
            result = await session.scalars(
                select(ScheduleCache)
                .where(
                    ScheduleCache.group_code == group_code,
                    ScheduleCache.lesson_date == target,
                )
                .order_by(ScheduleCache.lesson_start, ScheduleCache.subject)
            )
            return list(result)

    async def cleanup_schedule_cache(self, group_code: str | None = None) -> None:
        async with SessionFactory() as session:
            stmt = ScheduleCache.__table__.delete().where(
                ScheduleCache.lesson_date < local_today() - timedelta(days=1)
            )
            if group_code:
                stmt = stmt.where(ScheduleCache.group_code == group_code)
            await session.execute(stmt)
            await session.commit()
