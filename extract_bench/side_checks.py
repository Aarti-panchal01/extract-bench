"""Side checks, outside the main protocol. Not used in any ranking.

1. Does jusText recover on non-English pages when given the matching stoplist?
2. readability-lxml's default title() returns the whole <title> tag. How often
   does its short_title() helper (which strips " | Site Name") match the h1?

    python -m extract_bench.side_checks   # writes results/side_checks.json
"""

from __future__ import annotations

import json
from pathlib import Path

import justext

from . import build_corpus, metrics

STOPLIST = {"es": "Spanish", "de": "German", "fr": "French", "pt": "Portuguese", "it": "Italian", "hi": "Hindi"}
ROOT = Path(__file__).resolve().parent.parent


def justext_language_check() -> list[dict]:
    available = set(justext.get_stoplists())
    out = []
    for g in build_corpus.load_gold():
        if g["page_type"] != "non_english":
            continue
        html = build_corpus.load_html(g["doc_id"])
        name = STOPLIST[g["lang"]]
        row = {"doc_id": g["doc_id"], "lang": g["lang"], "split": g["split"], "stoplist": name,
               "stoplist_available": name in available}
        for label, sl in (("english_stoplist", "English"), ("matching_stoplist", name)):
            if sl not in available:
                row[label + "_f1"] = None
                continue
            paras = justext.justext(html.encode("utf-8"), justext.get_stoplist(sl), encoding="utf-8")
            text = "\n".join(p.text for p in paras if not p.is_boilerplate)
            row[label + "_f1"] = round(metrics.score({"title": None, "text": text}, g)["f1"], 3)
        out.append(row)
    return out


def readability_short_title_check() -> dict:
    from readability import Document

    rows = []
    for g in build_corpus.load_gold():
        if g["split"] != "test":
            continue
        doc = Document(build_corpus.load_html(g["doc_id"]))
        gold_t = metrics.norm_title(g["title"])
        rows.append({"doc_id": g["doc_id"],
                     "title_match": metrics.norm_title(doc.title()) == gold_t,
                     "short_title_match": metrics.norm_title(doc.short_title()) == gold_t,
                     "short_title": doc.short_title()})
    return {"n_test": len(rows),
            "title_matches": sum(r["title_match"] for r in rows),
            "short_title_matches": sum(r["short_title_match"] for r in rows),
            "misses": [r for r in rows if not r["short_title_match"]]}


if __name__ == "__main__":
    res = {"justext_language_check": justext_language_check(),
           "readability_short_title_check": readability_short_title_check()}
    path = ROOT / "results" / "side_checks.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in res["justext_language_check"]:
        print(r)
    rt = res["readability_short_title_check"]
    print(f"readability title(): {rt['title_matches']}/{rt['n_test']}, "
          f"short_title(): {rt['short_title_matches']}/{rt['n_test']}")
