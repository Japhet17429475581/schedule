from __future__ import annotations

import json

import httpx

from src.config import settings


class DeepSeekService:
    """Разбирает естественный запрос пользователя в структуру для расписания."""

    _SYSTEM_PROMPT = """
Ты — классификатор запросов для Telegram-бота расписания ВГСПУ.
Твоя задача — понять, хочет ли пользователь получить расписание,
и определить нужный период.

Разрешённые значения:

intent:
- "schedule" — пользователь хочет узнать расписание
- "unknown" — запрос не про расписание

date:
- "yesterday" — вчера
- "today" — сегодня
- "tomorrow" — завтра
- "this_week" — эта/текущая неделя
- "next_week" — следующая неделя
- "unknown" — другой день, конкретная дата или неопределённый период

Примеры:

"расписание на завтра"
{"intent":"schedule","date":"tomorrow"}

"что у меня сегодня по парам"
{"intent":"schedule","date":"today"}

"что было вчера"
{"intent":"schedule","date":"yesterday"}

"покажи расписание на эту неделю"
{"intent":"schedule","date":"this_week"}

"что у меня на следующей неделе"
{"intent":"schedule","date":"next_week"}

"скинь пары на след неделе"
{"intent":"schedule","date":"next_week"}

"что по учебе на этой неделе"
{"intent":"schedule","date":"this_week"}

Если пользователь просит конкретный день недели,
например "на понедельник", конкретную дату или период,
который не входит в разрешённые значения выше, используй:
{"intent":"schedule","date":"unknown"}

Если запрос не связан с расписанием:
{"intent":"unknown","date":"unknown"}

Верни ТОЛЬКО валидный JSON.
""".strip()

    async def parse(self, query: str) -> dict[str, str]:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY не задан")

        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {
                    "role": "system",
                    "content": self._SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": query.strip(),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 80,
            "thinking": {"type": "disabled"},
        }

        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(8.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        content = data["choices"][0]["message"].get("content") or "{}"

        result = json.loads(content)

        intent = result.get("intent")
        day = result.get("date")

        if intent not in {"schedule", "unknown"}:
            intent = "unknown"

        if day not in {
            "yesterday",
            "today",
            "tomorrow",
            "this_week",
            "next_week",
            "unknown",
        }:
            day = "unknown"

        return {
            "intent": intent,
            "date": day,
        }
