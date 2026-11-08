from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.database import UserRepository
from src.utils import esc

router = Router()
repo = UserRepository()


def percentage(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "нет данных"


@router.message(Command("stats"))
async def stats(message: Message):
    admins = {value.strip() for value in settings.admin_ids.split(",") if value.strip()}
    if str(message.from_user.id) not in admins:
        return
    activity = await repo.activity_stats()
    groups = await repo.group_stats()
    retention = "\n".join(
        f"D{day}: <b>{percentage(activity['retention'][f'd{day}']['pct'])}</b> "
        f"({activity['retention'][f'd{day}']['returned']}/{activity['retention'][f'd{day}']['eligible']})"
        for day in (1, 7, 30)
    )
    top_groups = "\n".join(f"• {esc(group)}: {count}" for group, count in groups[:10]) or "—"
    outcomes = activity["schedule_30d"]
    await message.answer(
        "📊 <b>Статистика</b> (МСК)\n\n"
        f"Пользователей: <b>{activity['total']}</b>\n"
        f"DAU / WAU / MAU: <b>{activity['active_today']} / {activity['active_7d']} / {activity['active_30d']}</b>\n"
        f"Новых сегодня / 7д / 30д: {activity['new_today']} / {activity['new_7d']} / {activity['new_30d']}\n"
        f"Вернулись сегодня: {activity['returning_today']}\n"
        f"Неактивны 30 дней: {activity['inactive_30d']}\n"
        f"Выбрали группу: {activity['with_group']} ({percentage(activity['group_selection_pct'])})\n"
        f"DAU/MAU: {percentage(activity['stickiness_pct'])}\n"
        f"Действий на активного сегодня: {activity['interactions_per_dau'] or 0}\n\n"
        f"<b>Retention — возврат ровно в день N</b>\n{retention}\n"
        "Только завершённые дни; в скобках вернулись / созревшая когорта.\n\n"
        f"<b>Запросы расписания за 30 дней</b>\n"
        f"Успешно: {outcomes['success']}\n"
        f"Нет на портале: {outcomes['unavailable']}\n"
        f"Ошибки: {outcomes['error']}\n"
        f"Успешность: {percentage(activity['schedule_success_pct'])}\n\n"
        f"<b>Топ групп</b>\n{top_groups}"
    )
