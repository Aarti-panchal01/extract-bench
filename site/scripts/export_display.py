"""Export display strings for the site, rounded from the full-precision result files.

Run from the repo root:  python site/scripts/export_display.py

site.json keeps numbers at 4 decimals. Rounding those again to 3 decimals in the
browser can differ from results/RESULTS.md by 0.001 when the 4th decimal is a 5
(double rounding). This file holds the 3-decimal strings formatted exactly the way
RESULTS.md formats them ("%.3f", "%+.3f"), straight from results/*.json, so the
text on the site and the result files cannot disagree. Charts still draw from
site.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results"
OUT = ROOT / "site" / "data" / "display.json"


def load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def f3(x):
    return f"{x:.3f}"


def ci(d):
    return {"mean": f3(d["mean"]), "lo": f3(d["lo"]), "hi": f3(d["hi"])}


def pair(d, key="mean_diff"):
    return {"diff": f"{d[key]:+.3f}", "lo": f"{d['lo']:+.3f}", "hi": f"{d['hi']:+.3f}"}


def main():
    s = load("summary.json")
    p = load("paired.json")
    w = load("wikipedia.json")
    z = load("zyte.json")

    syn = {}
    for r in s["summary"]:
        syn[r["extractor"]] = {
            "f1": ci(r["f1"]), "precision": f3(r["precision"]["mean"]),
            "recall": f3(r["recall"]["mean"]), "leak": f3(r["leak_rate"]["mean"]),
            "latency_ms": f"{r['latency_ms_median']:.2f}",
        }
    sens = p["sensitivity_without_listing"]
    no_listing = {r["extractor"]: ci(r["f1"]) for r in sens["ranking"]}

    wiki = {}
    for r in w["summary"]:
        wiki[r["extractor"]] = {"f1": ci(r["f1"]), "precision": f3(r["precision"]["mean"]),
                                "recall": f3(r["recall"]["mean"])}
    zyte = {}
    for r in z["summary"]:
        zyte[r["extractor"]] = {"f1": ci(r["f1"]), "f1_site": ci(z["site_ci"][r["extractor"]]),
                                "precision": f3(r["precision"]["mean"]), "recall": f3(r["recall"]["mean"])}

    out = {
        "synthetic": {
            "rows": syn,
            "no_listing": no_listing,
            "top_pair": {"page": pair(p), "type": pair(p["cluster_by_page_type"])},
            "no_listing_pair": {"page": pair(sens["paired_top_two"]),
                                "type": pair(sens["paired_top_two_cluster_by_page_type"])},
            "best_vs_default": pair(p["best_config_vs_default"]),
        },
        "wikipedia": {
            "rows": wiki,
            "vs_top": {k: pair(v) for k, v in w["paired"]["vs_top"].items()},
            "readability_minus_trafilatura_best": pair(w["paired"]["readability_minus_trafilatura_best"]),
        },
        "zyte": {
            "rows": zyte,
            "vs_top": {k: {"page": pair(v["page"]), "site": pair(v["site"])}
                       for k, v in z["paired"]["vs_top"].items()},
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
