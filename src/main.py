from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.database import close_db, init_db
from src.handlers import admin, group, inline, navigation, quick, schedule, start
from src.handlers.activity import ActivityMiddleware


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    activity = ActivityMiddleware()
    dispatcher.message.outer_middleware(activity)
    dispatcher.callback_query.outer_middleware(activity)
    dispatcher.inline_query.outer_middleware(activity)
    # Commands must take priority over the group-input state.
    dispatcher.include_routers(
        admin.router,
        start.router,
        group.router,
        navigation.router,
        schedule.router,
        quick.router,
        inline.router,
    )
    return dispatcher


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await init_db()
        await create_dispatcher().start_polling(bot, close_bot_session=False)
    finally:
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
