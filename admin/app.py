from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.database import UserRepository, close_db, init_db

from .auth import COOKIE_NAME, check_password, create_session_cookie, verify_session_cookie

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(title="Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

repo = UserRepository()


def _is_authed(request: Request) -> bool:
    return verify_session_cookie(request.cookies.get(COOKIE_NAME))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _is_authed(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    if not check_password(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный пароль"},
            status_code=401,
        )
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        create_session_cookie(),
        httponly=True,
        samesite="lax",
        secure=True,  # у вас https на кастомном домене — оставляем включённым
    )
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=302)

    total_users = await repo.count_users()
    activity = await repo.activity_stats()
    groups = await repo.group_stats()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total_users": total_users,
            "activity": activity,
            "groups": groups,
        },
    )
