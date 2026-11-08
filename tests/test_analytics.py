import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import func, inspect, select, text

from src.database.analytics import analytics_report
from src.database.migrations import migrate
from src.database.models import User, UserActivity, UserDailyActivity, UserStats
from src.database.repository import UserRepository


async def test_atomic_interaction_counters(database):
    _, factory = database
    repo = UserRepository()
    await asyncio.gather(
        *(repo.track_activity(123, "callback", "schedule:today") for _ in range(12))
    )
    await repo.track_activity(123, "message")
    await repo.track_activity(123, "inline")
    async with factory() as session:
        stats = await session.get(UserStats, 123)
        assert (stats.message_count, stats.callback_count) == (1, 12)
        daily = (await session.scalars(select(UserDailyActivity))).one()
        assert (daily.message_count, daily.callback_count, daily.inline_count) == (1, 12, 1)
        assert await session.scalar(select(func.count()).select_from(UserActivity)) == 14


async def test_outcomes_do_not_create_fake_active_users(database):
    _, factory = database
    await UserRepository().track_outcome(1, "schedule_success", "today")
    async with factory() as session:
        assert await session.get(UserStats, 1) is None
        assert await session.scalar(select(func.count()).select_from(UserDailyActivity)) == 0


async def test_empty_report_has_no_misleading_zero_retention(database):
    _, factory = database
    async with factory() as session:
        report = await analytics_report(session, date(2026, 11, 8))
    assert report["total"] == report["active_today"] == 0
    assert report["stickiness_pct"] is None
    assert report["schedule_success_pct"] is None
    assert all(metric["pct"] is None for metric in report["retention"].values())


async def test_calendar_windows_and_mature_exact_day_retention(database):
    _, factory = database
    today = date(2026, 11, 8)
    # Users 1/2 form a mature D30 cohort. User 3's D1 is still in progress today.
    async with factory() as session:
        for user, first_day, last_day in [
            (1, today - timedelta(days=32), today),
            (2, today - timedelta(days=32), today - timedelta(days=31)),
            (3, today - timedelta(days=1), today),
            (4, today, today),
        ]:
            session.add(
                UserStats(
                    telegram_id=user,
                    first_seen_at=datetime.combine(first_day, datetime.min.time()),
                    last_active_at=datetime.combine(last_day, datetime.min.time()),
                    message_count=1,
                    callback_count=0,
                )
            )
        for user, activity_day in [
            (1, today),
            (1, today - timedelta(days=31)),
            (1, today - timedelta(days=25)),
            (1, today - timedelta(days=2)),
            (2, today - timedelta(days=31)),
            (3, today),
            (4, today),
        ]:
            session.add(
                UserDailyActivity(telegram_id=user, activity_date=activity_day, message_count=1)
            )
        session.add(User(telegram_id=1, group_code="ИЯ-АВБ-111"))
        session.add_all(
            [
                UserActivity(telegram_id=1, event_type=event, created_at=datetime(2026, 11, 8, 1))
                for event in [
                    "schedule_success",
                    "schedule_success",
                    "schedule_unavailable",
                    "schedule_error",
                ]
            ]
        )
        await session.commit()
        report = await analytics_report(session, today)
    assert (report["active_today"], report["active_7d"], report["active_30d"]) == (3, 3, 3)
    assert (report["new_today"], report["new_7d"], report["returning_today"]) == (1, 2, 2)
    assert report["retention"]["d1"] == {"eligible": 2, "returned": 2, "pct": 100.0}
    assert report["retention"]["d7"] == {"eligible": 2, "returned": 1, "pct": 50.0}
    assert report["retention"]["d30"] == {"eligible": 2, "returned": 1, "pct": 50.0}
    assert report["cohorts"][0]["d1"] is None
    assert report["cohorts"][1]["d1"] is None
    assert report["inactive_30d"] == 1
    assert report["group_selection_pct"] == 25.0
    assert report["stickiness_pct"] == 100.0
    assert report["schedule_success_pct"] == 50.0


async def test_moscow_midnight_and_daily_backfill_migration(database):
    engine, factory = database
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN notifications_enabled BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN reminder_minutes INTEGER NOT NULL DEFAULT 30")
        )
        await conn.execute(User.__table__.insert().values(telegram_id=1, group_code="ИЯ-АВБ-111"))
        await conn.execute(
            UserActivity.__table__.insert(),
            [
                {
                    "telegram_id": 1,
                    "event_type": "message",
                    "created_at": datetime(2026, 11, 7, 21, 5),
                },
                {
                    "telegram_id": 1,
                    "event_type": "callback",
                    "created_at": datetime(2026, 11, 7, 22),
                },
                {
                    "telegram_id": 1,
                    "event_type": "schedule_success",
                    "created_at": datetime(2026, 11, 7, 22),
                },
            ],
        )
        await migrate(conn)
        await migrate(conn)
        columns = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("users")}
        )
        assert "notifications_enabled" not in columns
        assert "reminder_minutes" not in columns
    async with factory() as session:
        day = (await session.scalars(select(UserDailyActivity))).one()
        assert day.activity_date == date(2026, 11, 8)
        assert (day.message_count, day.callback_count) == (1, 1)
    # New users still insert after migrating legacy NOT NULL columns.
    await UserRepository().set_group(2, "МАТ-111")
    assert await UserRepository().get_group(1) == "ИЯ-АВБ-111"
    assert await UserRepository().get_group(2) == "МАТ-111"


async def test_retention_uses_moscow_cohort_day(database):
    _, factory = database
    async with factory() as session:
        session.add(
            UserStats(
                telegram_id=1,
                first_seen_at=datetime(2026, 11, 5, 22),
                last_active_at=datetime(2026, 11, 6, 22),
                message_count=2,
                callback_count=0,
            )
        )
        session.add(
            UserDailyActivity(telegram_id=1, activity_date=date(2026, 11, 7), message_count=1)
        )
        await session.commit()
        report = await analytics_report(session, date(2026, 11, 8))
    assert report["cohorts"][0]["date"] == "2026-11-06"
    assert report["retention"]["d1"]["pct"] == 100.0
