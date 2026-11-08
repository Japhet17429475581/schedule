from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    group_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UserActivity(Base):
    """Interaction and outcome events. Timestamps are UTC."""

    __tablename__ = "user_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        Index("ix_user_activity_user_created", "telegram_id", "created_at"),
        Index("ix_user_activity_created", "created_at"),
        Index("ix_user_activity_type_created", "event_type", "created_at"),
    )


class UserStats(Base):
    __tablename__ = "user_stats"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    callback_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("ix_user_stats_last_active", "last_active_at"),)


class UserDailyActivity(Base):
    """One row per user and Moscow calendar day, for retention and engagement."""

    __tablename__ = "user_daily_activity"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    activity_date: Mapped[date] = mapped_column(Date, primary_key=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    callback_count: Mapped[int] = mapped_column(Integer, default=0)
    inline_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("ix_user_daily_activity_date", "activity_date"),)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScheduleCache(Base):
    __tablename__ = "schedule_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_code: Mapped[str] = mapped_column(String(100), nullable=False)
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    lesson_start: Mapped[str] = mapped_column(String(5), nullable=False)
    lesson_end: Mapped[str] = mapped_column(String(5), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    lesson_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    teacher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cached_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        UniqueConstraint(
            "group_code",
            "lesson_date",
            "lesson_start",
            "subject",
            "teacher",
            "room",
            name="uq_schedule_cache_lesson",
        ),
        Index("ix_schedule_cache_group_date", "group_code", "lesson_date"),
        Index("ix_schedule_cache_date", "lesson_date"),
    )
