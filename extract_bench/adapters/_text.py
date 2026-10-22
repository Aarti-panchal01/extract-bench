"""Shared helper: turn an HTML fragment into plain text with block breaks."""

from __future__ import annotations

import lxml.html

BLOCK = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
    "table", "tr", "section", "article", "header", "footer", "aside", "nav", "main", "br",
    "dt", "dd", "figcaption",
}
CELL = {"td", "th"}


def html_fragment_to_text(fragment: str) -> str:
    if not fragment or not fragment.strip():
        return ""
    root = lxml.html.fromstring(fragment)
    out: list[str] = []

    def walk(el):
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in ("script", "style"):
            if el.tail:
                out.append(el.tail)
            return
        if tag in BLOCK:
            out.append("\n")
        if el.text:
            out.append(el.text)
        for child in el:
            walk(child)
        if tag in CELL:
            out.append(" | ")
        if tag in BLOCK:
            out.append("\n")
        if el.tail:
            out.append(el.tail)

    walk(root)
    text = "".join(out)
    lines = [ln.rstrip() for ln in text.split("\n")]
    # collapse runs of blank lines, keep indentation (matters for code)
    clean: list[str] = []
    for ln in lines:
        if ln.strip() == "" and (not clean or clean[-1] == ""):
            continue
        clean.append(ln if ln.strip() else "")
    return "\n".join(clean).strip("\n")
