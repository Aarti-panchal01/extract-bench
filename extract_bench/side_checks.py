"""Side check, outside the main protocol: does jusText recover on non-English
pages when given the matching stoplist? Not used in any ranking.

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


if __name__ == "__main__":
    res = {"justext_language_check": justext_language_check()}
    path = ROOT / "results" / "side_checks.json"
    path.write_text(json.dumps(res, indent=2))
    for r in res["justext_language_check"]:
        print(r)
