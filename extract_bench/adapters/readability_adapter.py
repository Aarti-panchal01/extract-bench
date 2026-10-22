from __future__ import annotations

from readability import Document

from ._text import html_fragment_to_text


def extract(html: str) -> dict:
    doc = Document(html)
    summary = doc.summary(html_partial=True)
    return {"title": doc.title(), "text": html_fragment_to_text(summary)}
