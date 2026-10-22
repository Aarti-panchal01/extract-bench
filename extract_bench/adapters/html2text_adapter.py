from __future__ import annotations

import html2text


def extract(html: str) -> dict:
    h = html2text.HTML2Text()
    h.body_width = 0
    return {"title": None, "text": h.handle(html)}
