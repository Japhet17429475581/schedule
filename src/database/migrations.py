"""Idempotent schema/data upgrades, run in the startup transaction."""

from sqlalchemy import case, func, inspect, select, text

from .analytics import local_date
from .models import SchemaMigration, UserActivity, UserDailyActivity

VERSION = "2026_11_daily_analytics_remove_notifications"


async def migrate(connection) -> None:
    applied = await connection.scalar(
        select(SchemaMigration.version).where(SchemaMigration.version == VERSION)
    )
    if applied:
        return
    columns = await connection.run_sync(
        lambda conn: {col["name"] for col in inspect(conn).get_columns("users")}
    )
    # Only feature-specific settings are removed; user/group and event history stay intact.
    for column in ("notifications_enabled", "reminder_minutes"):
        if column in columns:
            await connection.execute(text(f'ALTER TABLE users DROP COLUMN "{column}"'))
    # Backfill from observed interactions, never inventing visits from a last-active timestamp.
    activity_day = local_date(UserActivity.created_at, connection.dialect.name)
    counters = [
        func.sum(case((UserActivity.event_type == event, 1), else_=0))
        for event in ("message", "callback", "inline")
    ]
    await connection.execute(
        UserDailyActivity.__table__.insert().from_select(
            ["telegram_id", "activity_date", "message_count", "callback_count", "inline_count"],
            select(UserActivity.telegram_id, activity_day, *counters)
            .where(UserActivity.event_type.in_(("message", "callback", "inline")))
            .group_by(UserActivity.telegram_id, activity_day),
        )
    )
    # create_all does not add an index to an existing table.
    for index in UserActivity.__table__.indexes:
        await connection.run_sync(lambda conn, index=index: index.create(conn, checkfirst=True))
    await connection.execute(SchemaMigration.__table__.insert().values(version=VERSION))
