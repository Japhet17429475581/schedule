from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message

from src.database import UserRepository


class ActivityMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.repo = UserRepository()

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            if isinstance(event, CallbackQuery):
                event_type = "callback"
                details = event.data
            elif isinstance(event, Message):
                event_type = "message"
                # Store commands rather than arbitrary user messages.
                details = (
                    event.text.split()[0][:100]
                    if event.text and event.text.startswith("/")
                    else None
                )
            elif isinstance(event, InlineQuery):
                event_type = "inline"
                details = None
            else:
                event_type = "event"
                details = None
            try:
                await self.repo.track_activity(user.id, event_type, details)
            except Exception:
                # Аналитика никогда не должна ломать основной бот.
                logging.getLogger(__name__).exception("Could not record user activity")
        return await handler(event, data)
