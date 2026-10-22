from __future__ import annotations

import justext


def extract(html: str) -> dict:
    paras = justext.justext(html.encode("utf-8"), justext.get_stoplist("English"), encoding="utf-8")
    text = "\n".join(p.text for p in paras if not p.is_boilerplate)
    return {"title": None, "text": text}
