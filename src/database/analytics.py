from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, case, cast, distinct, exists, func, literal, select

from src.utils.dates import LOCAL_TZ, local_today

from .models import User, UserActivity, UserDailyActivity, UserStats


def percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 2) if denominator else None


def local_date(column, dialect: str):
    if dialect == "sqlite":
        return func.date(column, "+3 hours")
    return cast(func.timezone("Europe/Moscow", func.timezone("UTC", column)), Date)


async def analytics_report(session, today: date | None = None) -> dict:
    today = today or local_today()
    dialect = session.bind.dialect.name
    first_day = local_date(UserStats.first_seen_at, dialect)
    midnight = (
        datetime.combine(today, time.min, LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    )
    scalar = session.scalar
    total = int(await scalar(select(func.count()).select_from(UserStats)) or 0)
    report = {"total": total, "date": today.isoformat(), "timezone": "Europe/Moscow"}
    for name, days in (("active_today", 1), ("active_7d", 7), ("active_30d", 30)):
        report[name] = int(
            await scalar(
                select(func.count(distinct(UserDailyActivity.telegram_id))).where(
                    UserDailyActivity.activity_date >= today - timedelta(days=days - 1),
                    UserDailyActivity.activity_date <= today,
                )
            )
            or 0
        )
    for name, days in (("new_today", 1), ("new_7d", 7), ("new_30d", 30)):
        report[name] = int(
            await scalar(
                select(func.count())
                .select_from(UserStats)
                .where(
                    UserStats.first_seen_at >= midnight - timedelta(days=days - 1),
                    UserStats.first_seen_at < midnight + timedelta(days=1),
                )
            )
            or 0
        )
    report["returning_today"] = int(
        await scalar(
            select(func.count())
            .select_from(UserDailyActivity)
            .join(
                UserStats,
                UserStats.telegram_id == UserDailyActivity.telegram_id,
            )
            .where(UserDailyActivity.activity_date == today, UserStats.first_seen_at < midnight)
        )
        or 0
    )
    report["inactive_30d"] = int(
        await scalar(
            select(func.count())
            .select_from(UserStats)
            .where(
                UserStats.last_active_at < midnight - timedelta(days=29),
            )
        )
        or 0
    )
    report["with_group"] = int(
        await scalar(
            select(func.count())
            .select_from(UserStats)
            .join(
                User,
                User.telegram_id == UserStats.telegram_id,
            )
            .where(User.group_code.is_not(None))
        )
        or 0
    )
    report["group_selection_pct"] = percent(report["with_group"], total)
    report["stickiness_pct"] = percent(report["active_today"], report["active_30d"])
    for name, column in (
        ("messages", UserStats.message_count),
        ("callbacks", UserStats.callback_count),
    ):
        report[name] = int(await scalar(select(func.sum(column))) or 0)
    interactions = (
        UserDailyActivity.message_count
        + UserDailyActivity.callback_count
        + UserDailyActivity.inline_count
    )
    report["interactions_today"] = int(
        await scalar(
            select(func.sum(interactions)).where(
                UserDailyActivity.activity_date == today,
            )
        )
        or 0
    )
    report["interactions_per_dau"] = (
        round(report["interactions_today"] / report["active_today"], 2)
        if report["active_today"]
        else None
    )
    outcomes = dict(
        (
            await session.execute(
                select(UserActivity.event_type, func.count())
                .where(
                    UserActivity.created_at >= midnight - timedelta(days=29),
                    UserActivity.created_at < midnight + timedelta(days=1),
                    UserActivity.event_type.in_(
                        ("schedule_success", "schedule_unavailable", "schedule_error")
                    ),
                )
                .group_by(UserActivity.event_type)
            )
        ).all()
    )
    report["schedule_30d"] = {
        name: int(outcomes.get("schedule_" + name, 0))
        for name in ("success", "unavailable", "error")
    }
    requests = sum(report["schedule_30d"].values())
    report["schedule_success_pct"] = percent(report["schedule_30d"]["success"], requests)
    report["schedule_requests_30d"] = requests

    # Exact-day retention. Only fully completed target days enter the denominator.
    report["retention"] = {}
    returned = {}
    mature = {}
    for days in (1, 7, 30):
        target_day = (
            func.date(UserStats.first_seen_at, "+3 hours", f"+{days} days")
            if dialect == "sqlite"
            else first_day + literal(days)
        )
        mature[days] = (
            first_day < (today - timedelta(days=days)).isoformat()
            if dialect == "sqlite"
            else first_day < today - timedelta(days=days)
        )
        returned[days] = exists(
            select(1).where(
                UserDailyActivity.telegram_id == UserStats.telegram_id,
                UserDailyActivity.activity_date == target_day,
            )
        ).correlate(UserStats)
        eligible = int(
            await scalar(select(func.count()).select_from(UserStats).where(mature[days])) or 0
        )
        retained = int(
            await scalar(
                select(func.count()).select_from(UserStats).where(mature[days], returned[days])
            )
            or 0
        )
        report["retention"][f"d{days}"] = {
            "eligible": eligible,
            "returned": retained,
            "pct": percent(retained, eligible),
        }

    cohorts = await session.execute(
        select(
            first_day.label("cohort_date"),
            func.count().label("users"),
            *(
                func.sum(case((returned[days], 1), else_=0)).label(f"d{days}")
                for days in (1, 7, 30)
            ),
        )
        .select_from(UserStats)
        .group_by(first_day)
        .order_by(first_day.desc())
        .limit(60)
    )
    report["cohorts"] = []
    for row in cohorts.mappings():
        cohort_date = date.fromisoformat(str(row["cohort_date"]))
        cohort = {"date": cohort_date.isoformat(), "users": row["users"]}
        for days in (1, 7, 30):
            ready = cohort_date + timedelta(days=days) < today
            cohort[f"d{days}"] = percent(int(row[f"d{days}"]), row["users"]) if ready else None
        report["cohorts"].append(cohort)
    daily = await session.execute(
        select(
            UserDailyActivity.activity_date,
            func.count().label("active"),
            func.sum(interactions).label("interactions"),
        )
        .where(
            UserDailyActivity.activity_date >= today - timedelta(days=29),
            UserDailyActivity.activity_date <= today,
        )
        .group_by(UserDailyActivity.activity_date)
        .order_by(UserDailyActivity.activity_date.desc())
    )
    report["daily"] = [
        {"date": str(day), "active": active, "interactions": count} for day, active, count in daily
    ]
    return report
