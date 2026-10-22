from __future__ import annotations

from markdownify import markdownify


def extract(html: str) -> dict:
    return {"title": None, "text": markdownify(html)}
