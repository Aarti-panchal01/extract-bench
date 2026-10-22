from __future__ import annotations

import trafilatura


def _run(html: str, **opts) -> dict:
    doc = trafilatura.bare_extraction(html, with_metadata=True, **opts)
    if doc is None:
        return {"title": None, "text": ""}
    text = doc.text or ""
    if getattr(doc, "comments", None):
        # trafilatura's own txt output appends comments after the body
        text = text + "\n" + doc.comments
    return {"title": doc.title, "text": text}


def extract(html: str) -> dict:
    """Library defaults (include_comments=True, include_tables=True)."""
    return _run(html)


def make_configured(**opts):
    """Return an extract() bound to specific options (used for best-config)."""

    def extract_configured(html: str) -> dict:
        return _run(html, **opts)

    extract_configured.options = dict(opts)  # type: ignore[attr-defined]
    return extract_configured
