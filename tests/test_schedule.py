from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from src.parsers import ScheduleParser
from src.parsers.vspu import ScheduleNotFoundError
from src.services.schedule import ScheduleNotAvailableError, ScheduleService
from src.utils.dates import local_today

HEADERS = (
    "<tr><th>Дата</th><th>Время</th><th>Предмет</th><th>Преподаватель</th><th>Аудитория</th></tr>"
)


def table(rows=""):
    return "<table>" + HEADERS + rows + "</table>"


def service():
    instance = ScheduleService()
    instance._repo = AsyncMock()
    instance._repo.get_schedule_cache.return_value = []
    return instance


def test_portal_no_data_response_is_absent_not_a_free_day():
    with pytest.raises(ScheduleNotFoundError):
        ScheduleParser().parse(
            '<table class="schedule__table"><p class="no-data">Расписание не найдено</p></table>'
        )


def test_empty_published_week_is_valid():
    assert ScheduleParser().parse(table()) == []


def test_empty_teacher_keeps_room_in_correct_column():
    lessons = ScheduleParser().parse(
        table(
            "<tr><td>ПН 02.11</td></tr><tr><td>9:40 - 11:10</td><td>Самостоятельная работа студентов</td><td></td><td>1201</td></tr>"
        )
    )
    assert len(lessons) == 1
    assert lessons[0].teacher == ""
    assert lessons[0].room == "1201"
    assert lessons[0].start == "09:40"


def test_invalid_day_does_not_attach_lessons_to_previous_date():
    lessons = ScheduleParser().parse(
        table(
            "<tr><td>ПН 02.11</td></tr><tr><td>ПН 31.04</td></tr>"
            "<tr><td>9:40 - 11:10</td><td>лек Математика</td><td></td><td></td></tr>"
        )
    )
    assert lessons == []


def test_date_and_first_lesson_can_share_a_row():
    lessons = ScheduleParser().parse(
        table(
            '<tr><td rowspan="2">ПН 02.11</td><td>9:40 - 11:10</td><td>лек Математика</td><td>Иванов</td><td>1201</td></tr>'
        )
    )
    assert len(lessons) == 1
    assert lessons[0].subject == "Математика"


async def test_absent_schedule_is_translated_and_never_cached():
    instance = service()
    instance._fetch_html = AsyncMock(return_value="<html>Расписание не найдено</html>")
    for _ in range(2):
        with pytest.raises(ScheduleNotAvailableError):
            await instance.get_schedule("ИЯ-АВБ-111")
    assert instance._fetch_html.await_count == 2
    instance._repo.save_schedule_cache.assert_not_awaited()


async def test_http_404_is_absent_and_503_is_portal_error():
    instance = service()
    request = httpx.Request("GET", "https://portal.vspu.ru/schedule/students")
    for code, expected in [(404, ScheduleNotAvailableError), (503, httpx.HTTPStatusError)]:
        instance._fetch_html = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "portal error",
                request=request,
                response=httpx.Response(code, request=request),
            )
        )
        with pytest.raises(expected):
            await instance.get_schedule("ИЯ-АВБ-111")


async def test_validation_checks_neighbor_weeks():
    instance = service()
    instance.get_schedule = AsyncMock(side_effect=[ScheduleNotAvailableError(), []])
    assert await instance.validate_group("ИЯ-АВБ-111")
    assert instance.get_schedule.await_count == 2


async def test_validation_preserves_portal_failure():
    instance = service()
    instance.get_schedule = AsyncMock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(httpx.ConnectError):
        await instance.validate_group("ИЯ-АВБ-111")


async def test_validation_reports_missing_after_all_weeks():
    instance = service()
    instance.get_schedule = AsyncMock(side_effect=ScheduleNotAvailableError())
    assert not await instance.validate_group("ИЯ-АВБ-111")
    assert instance.get_schedule.await_count == 4


async def test_persistent_cache_failure_does_not_hide_valid_schedule():
    instance = service()
    instance._fetch_html = AsyncMock(return_value=table())
    instance._repo.save_schedule_cache.side_effect = RuntimeError("DB cache unavailable")
    assert await instance.get_schedule("ИЯ-АВБ-111") == []


async def test_cached_past_day_cannot_truncate_week_response():
    instance = service()
    target = local_today() - timedelta(days=1)
    instance._repo.get_schedule_cache.return_value = []
    instance._fetch_html = AsyncMock(return_value=table())
    assert await instance.week("ИЯ-АВБ-111", target) == []
    instance._fetch_html.assert_awaited_once()
