import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["BOT_TOKEN"] = "123456789:TEST_TOKEN_FOR_OFFLINE_CHECKS"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["ADMIN_SECRET_KEY"] = "test-secret"

from src.database.models import Base  # noqa: E402

DATABASES = ["sqlite"] + (["postgresql"] if os.getenv("TEST_DATABASE_URL") else [])


@pytest.fixture(params=DATABASES)
async def database(request, tmp_path, monkeypatch):
    schema = "test_" + uuid.uuid4().hex
    if request.param == "postgresql":
        control = create_async_engine(os.environ["TEST_DATABASE_URL"])
        async with control.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            os.environ["TEST_DATABASE_URL"],
            connect_args={
                "server_settings": {"search_path": schema, "timezone": "UTC"},
            },
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("src.database.repository.SessionFactory", factory)
    yield engine, factory
    await engine.dispose()
    if request.param == "postgresql":
        async with control.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()
