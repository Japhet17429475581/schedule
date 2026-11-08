from httpx import ASGITransport, AsyncClient

from admin.app import app
from admin.auth import COOKIE_NAME, create_session_cookie
from src.database import UserRepository


async def test_admin_requires_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


async def test_startup_and_authenticated_dashboard(database, monkeypatch):
    engine, _ = database
    monkeypatch.setattr("src.database.session.engine", engine)
    async with app.router.lifespan_context(app):
        await UserRepository().track_activity(1, "message")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            cookies={COOKIE_NAME: create_session_cookie()},
        ) as client:
            response = await client.get("/")
        assert response.status_code == 200
        assert "Retention" in response.text
        assert "DAU" in response.text
        assert "Напоминания" not in response.text
