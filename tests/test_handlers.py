from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.handlers import group, inline, quick, schedule
from src.keyboards import settings_menu
from src.services.schedule import NOT_AVAILABLE_TEXT, PORTAL_DOWN_TEXT, ScheduleNotAvailableError


@pytest.mark.parametrize(
    "module, method", [(schedule, "render_for_user"), (quick, "send_schedule")]
)
async def test_callback_and_quick_show_missing_schedule(module, method, monkeypatch):
    repo = AsyncMock()
    repo.get_group.return_value = "ИЯ-АВБ-111"
    monkeypatch.setattr(module, "repo", repo)
    monkeypatch.setattr(
        module.schedule_service, "day", AsyncMock(side_effect=ScheduleNotAvailableError())
    )
    if module is schedule:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1), data="schedule:today", answer=AsyncMock()
        )
        edit = AsyncMock()
        monkeypatch.setattr(module, "safe_edit", edit)
        await module.schedule_callback(callback, AsyncMock())
        assert edit.call_args.args[1] == NOT_AVAILABLE_TEXT
    else:
        message = SimpleNamespace(from_user=SimpleNamespace(id=1), answer=AsyncMock())
        await getattr(module, method)(message, "today")
        assert message.answer.call_args.args[0] == NOT_AVAILABLE_TEXT
    repo.track_outcome.assert_awaited_once_with(1, "schedule_unavailable", "today")


async def test_refresh_preserves_week_offset(monkeypatch):
    repo = AsyncMock()
    repo.get_group.return_value = "ИЯ-АВБ-111"
    monkeypatch.setattr(schedule, "repo", repo)
    render = AsyncMock()
    monkeypatch.setattr(schedule, "render_for_user", render)
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="schedule:refresh:week:1", answer=AsyncMock()
    )
    await schedule.refresh_current(callback, AsyncMock())
    render.assert_awaited_once_with(callback, "week:1", force_refresh=True)


@pytest.mark.parametrize(
    "available, error, expected",
    [(False, None, NOT_AVAILABLE_TEXT), (None, httpx.ConnectError("offline"), PORTAL_DOWN_TEXT)],
)
async def test_group_selection_explains_absence_or_portal_failure(
    available, error, expected, monkeypatch
):
    validate = AsyncMock(return_value=available, side_effect=error)
    monkeypatch.setattr(group.schedule_service, "validate_group", validate)
    repo = AsyncMock()
    monkeypatch.setattr(group, "repo", repo)
    checking = SimpleNamespace(edit_text=AsyncMock())
    message = SimpleNamespace(
        text="ИЯ-АВБ-111", from_user=SimpleNamespace(id=1), answer=AsyncMock(return_value=checking)
    )
    state = AsyncMock()
    await group.group_input(message, state)
    assert expected in checking.edit_text.call_args.args[0]
    repo.set_group.assert_not_awaited()
    state.clear.assert_not_awaited()


async def test_inline_absence_uses_same_message(monkeypatch):
    monkeypatch.setattr(inline.repo, "get_group", AsyncMock(return_value="ИЯ-АВБ-111"))
    monkeypatch.setattr(inline.repo, "track_outcome", AsyncMock())
    monkeypatch.setattr(
        inline.schedule_service, "day", AsyncMock(side_effect=ScheduleNotAvailableError())
    )
    answer = AsyncMock()
    query = SimpleNamespace(query="сегодня", from_user=SimpleNamespace(id=1), answer=answer)
    await inline.inline_schedule(query)
    assert answer.call_args.args[0][0].input_message_content.message_text == NOT_AVAILABLE_TEXT


async def test_llm_week_intent_is_rendered_as_week(monkeypatch):
    monkeypatch.setattr(inline.repo, "get_group", AsyncMock(return_value="ИЯ-АВБ-111"))
    monkeypatch.setattr(inline.repo, "track_outcome", AsyncMock())
    monkeypatch.setattr(
        inline.deepseek,
        "parse",
        AsyncMock(return_value={"intent": "schedule", "date": "next_week"}),
    )
    week = AsyncMock(return_value=[])
    monkeypatch.setattr(inline.schedule_service, "week", week)
    query = SimpleNamespace(
        query="что на следующей неделе", from_user=SimpleNamespace(id=1), answer=AsyncMock()
    )
    await inline.inline_schedule(query)
    week.assert_awaited_once()
    assert "Неделя" in query.answer.call_args.args[0][0].input_message_content.message_text


def test_dispatcher_import_and_required_routers():
    from src.main import create_dispatcher

    assert set(create_dispatcher().resolve_used_update_types()) == {
        "message",
        "callback_query",
        "inline_query",
    }


def test_settings_have_no_notification_controls():
    assert all(
        not (button.callback_data or "").startswith("reminder:")
        for row in settings_menu().inline_keyboard
        for button in row
    )
