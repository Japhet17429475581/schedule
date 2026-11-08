from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from datetime import datetime as dt

from bs4 import BeautifulSoup

from src.utils.dates import local_today

DAY_RE = re.compile(
    r"^(ПН|ВТ|СР|ЧТ|ПТ|СБ|ВС)\s+(\d{1,2})\.(\d{1,2})$",
    re.I,
)

TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})")

TYPE_RE = re.compile(
    r"^(лек|пр|лпз|лаб|сем|конс|к|экз|зач|диф\.?\s*зач)\s+",
    re.I,
)

TYPE_MAP = {
    "лек": "lecture",
    "пр": "practice",
    "лпз": "practice",
    "лаб": "lab",
    "сем": "seminar",
    "конс": "consultation",
    "к": "consultation",
    "экз": "exam",
    "зач": "credit",
    "диф.зач": "credit",
}


class ScheduleNotFoundError(Exception):
    """Расписание не найдено на портале."""

    pass


@dataclass(slots=True, frozen=True)
class Lesson:
    date: date
    start: str
    end: str
    subject: str
    lesson_type: str | None
    teacher: str
    room: str


class ScheduleParser:
    def parse(self, content: str) -> list[Lesson]:
        soup = BeautifulSoup(content, "html.parser")
        table = self._find_schedule_table(soup)

        if table is None:
            raise ScheduleNotFoundError("Расписание не найдено на портале")

        lessons: list[Lesson] = []
        current_date: date | None = None

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])

            if not cells:
                continue

            values = [self.clean_text(c.get_text(" ", strip=True)) for c in cells]
            if not any(values):
                continue

            detected = self._parse_day(values)

            if detected:
                current_date = detected

            # Строка похожа на день, но дата невалидна (например, 31.04):
            # пропускаем её вместе с занятиями, чтобы они не прилипли
            # к предыдущему дню.
            if not detected and any(DAY_RE.match(v) for v in values):
                current_date = None
                continue

            if self._looks_like_header(values):
                continue

            if current_date is None:
                continue

            lesson = self._parse_lesson(values, current_date)

            if lesson:
                lessons.append(lesson)

        return self._deduplicate(lessons)

    def _find_schedule_table(self, soup: BeautifulSoup):
        tables = soup.find_all("table")

        required = (
            "дата",
            "время",
            "предмет",
            "преподаватель",
            "аудитория",
        )

        for table in tables:
            text = self.clean_text(table.get_text(" ", strip=True)).lower()

            if all(item in text for item in required):
                return table

        for table in tables:
            text = self.clean_text(table.get_text(" ", strip=True))

            if re.search(
                r"(?:ПН|ВТ|СР|ЧТ|ПТ|СБ|ВС)\s+\d{1,2}\.\d{1,2}",
                text,
                re.I,
            ) and TIME_RE.search(text):
                return table

        return None

    def _parse_day(self, values: list[str]) -> date | None:
        for value in values:
            match = DAY_RE.match(value)

            if not match:
                continue

            day = int(match.group(2))
            month = int(match.group(3))

            return self._resolve_year(day, month)

        return None

    @staticmethod
    def _resolve_year(day: int, month: int) -> date | None:
        today = local_today()

        candidates: list[date] = []

        for year in (today.year - 1, today.year, today.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda item: abs((item - today).days),
        )

    def _parse_lesson(
        self,
        values: list[str],
        lesson_date: date,
    ) -> Lesson | None:

        time_index = None
        match = None

        for index, value in enumerate(values):
            match = TIME_RE.search(value)

            if match:
                time_index = index
                break

        if match is None or time_index is None:
            return None

        start, end = match.group(1), match.group(2)
        try:
            start = dt.strptime(start, "%H:%M").strftime("%H:%M")
            end = dt.strptime(end, "%H:%M").strftime("%H:%M")
        except ValueError:
            return None

        after = values[time_index + 1 :]

        if not after:
            return None

        subject_raw = after[0]

        if DAY_RE.match(subject_raw):
            return None

        subject, lesson_type = self._split_type(subject_raw)

        if not subject:
            return None

        teacher = after[1] if len(after) > 1 else ""
        room = after[2] if len(after) > 2 else ""

        return Lesson(
            date=lesson_date,
            start=start,
            end=end,
            subject=subject,
            lesson_type=lesson_type,
            teacher=teacher,
            room=room,
        )

    @staticmethod
    def _split_type(value: str) -> tuple[str, str | None]:
        match = TYPE_RE.match(value)

        if not match:
            return value.strip(), None

        raw = re.sub(r"\s+", "", match.group(1).lower()).replace("ё", "е")

        lesson_type = TYPE_MAP.get(raw)

        return (
            value[match.end() :].strip(),
            lesson_type,
        )

    @staticmethod
    def _looks_like_header(values: list[str]) -> bool:
        joined = " ".join(values).lower()

        return "дата" in joined and "время" in joined and "предмет" in joined

    @staticmethod
    def clean_text(value: str) -> str:
        for char in (
            "\u200b",
            "\u200c",
            "\u200d",
            "\ufeff",
            "\xa0",
        ):
            value = value.replace(char, " ")

        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _deduplicate(
        lessons: list[Lesson],
    ) -> list[Lesson]:

        unique = {
            (
                x.date,
                x.start,
                x.end,
                x.subject,
                x.lesson_type,
                x.teacher,
                x.room,
            ): x
            for x in lessons
        }

        def sort_key(lesson: Lesson):
            start_time = dt.strptime(
                lesson.start,
                "%H:%M",
            ).time()

            return (
                lesson.date,
                start_time,
                lesson.subject,
            )

        return sorted(
            unique.values(),
            key=sort_key,
        )
