"""Статистика бота на русском языке; --json для машинного отчёта."""

import argparse
import asyncio
import json
import sys
from datetime import date


def number(value: int | float | None) -> str:
    if value is None:
        return "нет данных"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def percentage(value: float | None) -> str:
    return f"{number(value)}%" if value is not None else "нет данных"


def report_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%d.%m.%Y")


def format_report(report: dict) -> str:
    lines = [
        "=" * 64,
        "СТАТИСТИКА БОТА РАСПИСАНИЯ ВГСПУ",
        f"Дата: {report_date(report['date'])}. Время и границы дней — московские.",
        "Подключение к базе данных: успешно.",
        "=" * 64,
    ]

    def section(title: str) -> None:
        lines.extend(["", title, "-" * 64])

    section("1. ПОЛЬЗОВАТЕЛИ")
    lines.extend(
        [
            f"Всего пользователей в истории активности: {number(report['total'])}",
            f"Из них выбрали группу: {number(report['with_group'])} "
            f"({percentage(report['group_selection_pct'])})",
            f"Не пользовались ботом последние 30 дней: {number(report['inactive_30d'])}",
        ]
    )

    section("2. СКОЛЬКО ЛЮДЕЙ ПОЛЬЗУЕТСЯ БОТОМ")
    lines.extend(
        [
            f"За сегодня (DAU): {number(report['active_today'])}",
            f"За последние 7 дней (WAU): {number(report['active_7d'])}",
            f"За последние 30 дней (MAU): {number(report['active_30d'])}",
            "Один человек учитывается один раз за период, сколько бы кнопок он ни нажал.",
            "Периоды в 7 и 30 дней включают сегодняшний день.",
            "",
            f"Впервые пришли сегодня: {number(report['new_today'])}",
            f"Впервые пришли за 7 дней: {number(report['new_7d'])}",
            f"Впервые пришли за 30 дней: {number(report['new_30d'])}",
            f"Вернулись сегодня после предыдущих посещений: {number(report['returning_today'])}",
            "Новый пользователь — тот, чьё первое действие есть в доступной истории.",
        ]
    )

    section("3. КАК АКТИВНО ПОЛЬЗУЮТСЯ БОТОМ")
    lines.extend(
        [
            f"Сообщений от пользователей за всё время: {number(report['messages'])}",
            f"Нажатий кнопок за всё время: {number(report['callbacks'])}",
            f"Действий сегодня: {number(report['interactions_today'])}",
            "Действия — сообщения, нажатия кнопок и запросы через inline-режим.",
            f"В среднем действий на одного активного сегодня: {number(report['interactions_per_dau'])}",
            f"Какая доля месячной аудитории зашла сегодня: {percentage(report['stickiness_pct'])}",
            "Последний показатель — это DAU / MAU.",
        ]
    )

    section("4. ВОЗВРАЩАЮТСЯ ЛИ ЛЮДИ В БОТ (RETENTION)")
    lines.append("Считаем возврат ровно на нужный день после первого посещения:")
    for day, label in [
        (1, "На следующий день (D1)"),
        (7, "На 7-й день (D7)"),
        (30, "На 30-й день (D30)"),
    ]:
        metric = report["retention"][f"d{day}"]
        if metric["eligible"]:
            lines.append(
                f"{label}: {percentage(metric['pct'])} — вернулись "
                f"{number(metric['returned'])} из {number(metric['eligible'])} пользователей."
            )
        else:
            lines.append(f"{label}: пока нет данных — нужный день ещё не завершился ни у кого.")
    lines.extend(
        [
            "В расчёт входят только пользователи, у которых день возврата уже закончился.",
            "Например, D7 = 20% означает: на 7-й день вернулись 20 из каждых 100.",
        ]
    )

    section("5. КАК БОТ ВЫДАЁТ РАСПИСАНИЕ — ЗА 30 ДНЕЙ")
    outcomes = report["schedule_30d"]
    lines.extend(
        [
            f"Всего запросов с записанным результатом: {number(report['schedule_requests_30d'])}",
            f"Расписание получено: {number(outcomes['success'])}",
            f"Расписания нет на портале: {number(outcomes['unavailable'])}",
            f"Технические ошибки, включая недоступность портала: {number(outcomes['error'])}",
            f"Доля запросов с полученным расписанием: {percentage(report['schedule_success_pct'])}",
            "Отсутствие расписания на портале учитывается отдельно от технических ошибок.",
            "Результаты запросов собираются с момента установки обновления аналитики.",
        ]
    )

    section("6. АКТИВНОСТЬ ПО ДНЯМ — ЗА 30 ДНЕЙ")
    if report["daily"]:
        lines.append(f"{'Дата':<14} {'Пользователей':>14} {'Действий':>14}")
        for row in report["daily"]:
            lines.append(
                f"{report_date(row['date']):<14} {number(row['active']):>14} "
                f"{number(row['interactions']):>14}"
            )
        lines.append("Показаны дни, в которые были действия.")
    else:
        lines.append("За этот период действий пока нет.")

    section("7. ВОЗВРАТЫ ПО ДАТЕ ПЕРВОГО ПОСЕЩЕНИЯ")
    lines.append("Каждая строка — люди, которые впервые пришли в один день.")
    if report["cohorts"]:
        lines.append(f"{'Первый день':<14} {'Пришли':>8} {'D1':>12} {'D7':>12} {'D30':>12}")
        for row in report["cohorts"]:
            values = [
                percentage(row[f"d{day}"]) if row[f"d{day}"] is not None else "—"
                for day in (1, 7, 30)
            ]
            lines.append(
                f"{report_date(row['date']):<14} {number(row['users']):>8} "
                f"{values[0]:>12} {values[1]:>12} {values[2]:>12}"
            )
        lines.append("«—» означает: нужный день возврата ещё не закончился.")
        lines.append("Показаны последние 60 дат первого посещения, для которых есть пользователи.")
    else:
        lines.append("Истории посещений пока нет.")

    section("8. СКОЛЬКО ПОЛЬЗОВАТЕЛЕЙ В КАЖДОЙ ГРУППЕ")
    if report["groups"]:
        lines.append(f"Групп с пользователями: {number(len(report['groups']))}")
        for group, count in report["groups"]:
            lines.append(f"  {group}: {number(count)}")
    else:
        lines.append("Никто ещё не сохранил свою группу.")
    lines.extend(["", "=" * 64, "Отчёт готов."])
    return "\n".join(lines)


async def main(json_output: bool = False, count_only: bool = False) -> None:
    from src.database import UserRepository, close_db

    try:
        repo = UserRepository()
        if count_only:
            print(await repo.count_all_users())
            return
        report = await repo.activity_stats()
        report["groups"] = await repo.group_stats()
        if json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_report(report))
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Понятная статистика бота расписания на русском.")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Вывести данные в JSON вместо отчёта.")
    output.add_argument(
        "--count", action="store_true", help="Вывести только общее число пользователей."
    )
    parser.add_argument("--debug", action="store_true", help="Показать полную ошибку при сбое.")
    args = parser.parse_args()
    try:
        asyncio.run(main(json_output=args.json, count_only=args.count))
    except Exception:
        if args.debug:
            raise
        print(
            "Не удалось получить статистику.\n"
            "Проверь подключение к базе и DATABASE_URL в настройках.\n"
            "Если бот только обновлён, сначала запусти его для создания таблиц.\n"
            "Подробности ошибки: python check_db.py --debug",
            file=sys.stderr,
        )
        sys.exit(1)
