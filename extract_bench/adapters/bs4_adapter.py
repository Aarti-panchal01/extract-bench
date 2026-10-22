from __future__ import annotations

from bs4 import BeautifulSoup


def extract(html: str) -> dict:
    """The naive baseline: every string in the document, scripts and styles included."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else None
    return {"title": title, "text": soup.get_text("\n")}
