from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    portal_url: str
    database_url: str
    cache_ttl: int
    request_timeout: float
    admin_ids: str
    deepseek_api_key: str
    deepseek_model: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(f"Переменная окружения {name} не задана.")

    return value


def load_settings() -> Settings:
    return Settings(
        bot_token=_required("BOT_TOKEN"),
        portal_url=os.getenv(
            "PORTAL_URL",
            "https://portal.vspu.ru/schedule/students",
        ).strip(),
        database_url=_required("DATABASE_URL"),
        cache_ttl=int(
            os.getenv(
                "CACHE_TTL",
                str(60 * 60 * 24),
            )
        ),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "30")),
        admin_ids=os.getenv("ADMIN_IDS", ""),
        deepseek_api_key=os.getenv(
            "DEEPSEEK_API_KEY",
            "",
        ).strip(),
        deepseek_model=os.getenv(
            "DEEPSEEK_MODEL",
            "deepseek-v4-flash",
        ).strip(),
    )


settings = load_settings()
