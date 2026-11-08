from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "bug:report")
async def bug(c: CallbackQuery):
    await c.message.answer("🐛 Опиши ошибку следующим сообщением. Разработчик получит отчёт.")
    await c.answer()
