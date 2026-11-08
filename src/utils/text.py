from __future__ import annotations

import html


def esc(value: str) -> str:
    return html.escape(value or "")
