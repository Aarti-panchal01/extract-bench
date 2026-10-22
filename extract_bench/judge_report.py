"""Compare the metric rule with one or more saved LLM judge runs.

    python -m extract_bench.judge_report results/judge_a.json results/judge_b.json

Writes results/JUDGE.md: per-judge agreement with the metric rule, kappa with a
bootstrap CI, judge-vs-judge kappa on the shared items, the 2x2 tables, and
every item where a judge disagrees with the metric rule.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import stats
from .judge import kappa_ci

ROOT = Path(__file__).resolve().parent.parent


def _fmt_ci(ci) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "n/a"


def load(paths: list[Path]) -> list[dict]:
    runs = []
    for p in paths:
        r = json.loads(Path(p).read_text(encoding="utf-8"))
        if r.get("skipped"):
            continue
        r["_label"] = r.get("model") or r.get("judge") or Path(p).stem
        r["_file"] = Path(p).name
        runs.append(r)
    return runs


def pairwise(a: dict, b: dict) -> dict:
    ia = {(i["extractor"], i["doc_id"]): i["judge"] for i in a["items"]}
    ib = {(i["extractor"], i["doc_id"]): i["judge"] for i in b["items"]}
    keys = sorted(set(ia) & set(ib))
    la, lb = [ia[k] for k in keys], [ib[k] for k in keys]
    if not keys:
        return {"n": 0}
    return {"n": len(keys), "agreement": sum(x == y for x, y in zip(la, lb)) / len(keys),
            "cohen_kappa": stats.cohen_kappa(la, lb), "cohen_kappa_ci95": kappa_ci(la, lb)}


def unanimous_vs_metric(runs: list[dict]) -> dict:
    """Items where every judge gives the same label: how often the metric rule agrees."""
    maps = [{(i["extractor"], i["doc_id"]): i for i in r["items"]} for r in runs]
    keys = set(maps[0])
    for m in maps[1:]:
        keys &= set(m)
    same = [k for k in keys if len({m[k]["judge"] for m in maps}) == 1]
    agree = [k for k in same if maps[0][k]["judge"] == maps[0][k]["metric"]]
    return {"n_shared": len(keys), "n_judges_agree": len(same), "metric_agrees_with_them": len(agree),
            "disagreements": sorted(
                ({"extractor": k[0], "doc_id": k[1], "f1": maps[0][k]["f1"], "leak_rate": maps[0][k]["leak_rate"],
                  "metric": maps[0][k]["metric"], "judges": maps[0][k]["judge"]} for k in same if k not in agree),
                key=lambda d: (d["extractor"], d["doc_id"]))}


def report(runs: list[dict]) -> str:
    out = ["# LLM judge vs the metric rule", "",
           "Metric rule: GOOD when F1 >= 0.8 and leak rate <= 0.2, else BAD. "
           "Each judge sees the gold main text and the extractor output and answers GOOD or BAD. "
           "Test split only. Kappa CIs are a percentile bootstrap over items (2,000 resamples, seed 7).", ""]
    out += ["| Judge | n | errors | Agreement | Kappa [95% CI] | Metric GOOD | Judge GOOD |", "|---|---|---|---|---|---|---|"]
    for r in runs:
        out.append(f"| {r['_label']} | {r['n']} | {r['n_errors']} | {r['agreement']:.2f} | "
                   f"{r['cohen_kappa']:.2f} {_fmt_ci(r.get('cohen_kappa_ci95'))} | "
                   f"{r['metric_good_rate']:.2f} | {r['judge_good_rate']:.2f} |")
    out.append("")
    for r in runs:
        c = r["confusion"]
        out += [f"## {r['_label']} ({r['_file']}, {r['sampling']}, seed {r['seed']})", "",
                "| | judge GOOD | judge BAD |", "|---|---|---|",
                f"| metric GOOD | {c['metric_GOOD_judge_GOOD']} | {c['metric_GOOD_judge_BAD']} |",
                f"| metric BAD | {c['metric_BAD_judge_GOOD']} | {c['metric_BAD_judge_BAD']} |", "",
                "| Extractor | n | agree | metric GOOD | judge GOOD |", "|---|---|---|---|---|"]
        for ext, d in r["per_extractor"].items():
            out.append(f"| {ext} | {d['n']} | {d['agree']} | {d['metric_good']} | {d['judge_good']} |")
        out.append("")
    if len(runs) >= 2:
        out += ["## Judge vs judge", "", "| Pair | n | Agreement | Kappa [95% CI] |", "|---|---|---|---|"]
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                p = pairwise(runs[i], runs[j])
                if p["n"]:
                    out.append(f"| {runs[i]['_label']} vs {runs[j]['_label']} | {p['n']} | {p['agreement']:.2f} | "
                               f"{p['cohen_kappa']:.2f} {_fmt_ci(p['cohen_kappa_ci95'])} |")
        u = unanimous_vs_metric(runs)
        out += ["", f"Items judged by all: {u['n_shared']}. All judges gave the same label on {u['n_judges_agree']}; "
                f"the metric rule matches them on {u['metric_agrees_with_them']}.", "",
                "Items where the judges agree with each other but not with the metric rule:", "",
                "| Extractor | Page | F1 | Leak | Metric | Judges |", "|---|---|---|---|---|---|"]
        for d in u["disagreements"]:
            out.append(f"| {d['extractor']} | {d['doc_id']} | {d['f1']:.2f} | {d['leak_rate']:.2f} | "
                       f"{d['metric']} | {d['judges']} |")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "JUDGE.md")
    a = ap.parse_args(argv)
    runs = load(a.files)
    if not runs:
        print("no judge run with results (all skipped)")
        return 1
    a.out.write_text(report(runs), encoding="utf-8", newline="\n")
    print(a.out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
