from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

from .models import Base

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"server_settings": {"timezone": "UTC"}}
    if settings.database_url.startswith("postgresql")
    else {},
)

SessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    from .migrations import migrate

    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            await connection.execute(text("SELECT pg_advisory_xact_lock(76201108)"))
        await connection.run_sync(Base.metadata.create_all)
        await migrate(connection)


async def close_db() -> None:
    await engine.dispose()
