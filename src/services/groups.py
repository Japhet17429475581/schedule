from __future__ import annotations

import re

# Не зашиваем список групп в бизнес-логику: портал является источником истины.
# Это позволяет боту работать и с новой группой, которая появится на портале,
# даже если список групп на сайте университета изменится.
GROUP_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9./()\-]+$")


def normalize_group(value: str) -> str:
    return value.strip().upper().replace("–", "-").replace("—", "-")


def is_valid_group_format(value: str) -> bool:
    value = normalize_group(value)
    if not value or len(value) > 100:
        return False
    if not GROUP_RE.fullmatch(value):
        return False
    # Обычные группы содержат дефис; отдельные исторические значения вида
    # 1.1.5.1КУРС также разрешены порталом.
    return "-" in value or "КУРС" in value.upper()
