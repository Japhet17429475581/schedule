from __future__ import annotations

import hmac
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "admin_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12 часов

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY")

if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD is not set (add it to your .env)")
if not ADMIN_SECRET_KEY:
    raise RuntimeError("ADMIN_SECRET_KEY is not set (add it to your .env)")

_serializer = URLSafeTimedSerializer(ADMIN_SECRET_KEY, salt="admin-session")


def check_password(candidate: str) -> bool:
    """Сравнение с защитой от timing-атак."""
    return hmac.compare_digest(candidate.encode(), ADMIN_PASSWORD.encode())


def create_session_cookie() -> str:
    return _serializer.dumps({"authed": True})


def verify_session_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer.loads(value, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return bool(data.get("authed"))
