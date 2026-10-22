"""Run the benchmark end to end.

    python -m extract_bench.run            # full run, writes results/ and charts/
    python -m extract_bench.run --quick    # fewer bootstrap iterations, 1 timing repeat

Steps:
1. build the corpus (deterministic from the seed) if it is missing
2. tune trafilatura on the DEV split only and freeze the best config
3. run every adapter (plus the frozen best-config row) on all 60 pages
4. score, label failures, bootstrap CIs, paired test of the top two, on TEST only
5. write results/*.json, results/*.csv, results/RESULTS.md and charts/*.png

No network access is needed or used.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import adapters, build_corpus, metrics, stats, taxonomy
from .adapters import trafilatura_adapter as tfa

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
CHARTS = ROOT / "charts"

TUNING_GRID = [
    {"include_comments": c, "favor_precision": fp, "favor_recall": fr}
    for c in (True, False)
    for fp, fr in ((False, False), (True, False), (False, True))
]


def run_one(fn, html: str, repeats: int) -> tuple[dict, float, str | None]:
    """Return (output, median latency ms, error). Exceptions are failures, not crashes."""
    times = []
    out: dict = {"title": None, "text": ""}
    err = None
    for k in range(repeats):
        t0 = time.perf_counter()
        try:
            res = fn(html)
        except Exception as e:  # noqa: BLE001 - every library error counts as a failure row
            err = f"{type(e).__name__}: {e}"[:300]
            times.append((time.perf_counter() - t0) * 1000)
            break
        times.append((time.perf_counter() - t0) * 1000)
        if k == 0:
            if not isinstance(res, dict) or "text" not in res:
                err = "ContractError: adapter did not return {title, text}"
                break
            out = {"title": res.get("title"), "text": res.get("text") or ""}
    return out, statistics.median(times), err


def evaluate(fn, docs: list[dict], htmls: dict[str, str], repeats: int) -> list[dict]:
    rows = []
    for g in docs:
        out, ms, err = run_one(fn, htmls[g["doc_id"]], repeats)
        s = metrics.score(out, g)
        row = {"doc_id": g["doc_id"], "page_type": g["page_type"], "split": g["split"], "lang": g["lang"],
               "latency_ms": ms, "error": err, **s, "output_text": out["text"], "output_title": out["title"]}
        if err:
            for k in ("precision", "recall", "f1"):
                row[k] = 0.0
        row["labels"] = taxonomy.label(row)
        rows.append(row)
    return rows


def tune_trafilatura(dev: list[dict], htmls: dict[str, str]) -> tuple[dict, list[dict]]:
    log = []
    for opts in TUNING_GRID:
        rows = evaluate(tfa.make_configured(**opts), dev, htmls, repeats=1)
        f1 = statistics.mean(r["f1"] for r in rows)
        leak = statistics.mean(r["leak_rate"] for r in rows)
        log.append({"options": opts, "dev_f1": f1, "dev_leak_rate": leak})
    # highest dev F1; ties broken by lower leak, then by grid order (stable)
    best = sorted(log, key=lambda x: (-round(x["dev_f1"], 6), round(x["dev_leak_rate"], 6)))[0]
    return best["options"], log


def mean_or_none(vals):
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def summarize(name: str, rows: list[dict], iters: int, has_title: bool, config: str) -> dict:
    out = {"extractor": name, "config": config, "n_docs": len(rows)}
    for m in ("f1", "precision", "recall", "leak_rate"):
        out[m] = stats.bootstrap_ci([r[m] for r in rows], iters=iters)
    out["table_row_recall"] = mean_or_none(r["table_row_recall"] for r in rows)
    out["code_line_recall"] = mean_or_none(r["code_line_recall"] for r in rows)
    out["code_line_exact"] = mean_or_none(r["code_line_exact"] for r in rows)
    out["title_match"] = statistics.mean(r["title_match"] for r in rows) if has_title else None
    lat = sorted(r["latency_ms"] for r in rows)
    out["latency_ms_median"] = statistics.median(lat)
    out["latency_ms_p90"] = lat[min(len(lat) - 1, int(round(0.9 * (len(lat) - 1))))]
    out["n_errors"] = sum(1 for r in rows if r["error"])
    out["n_docs_with_any_failure"] = sum(1 for r in rows if r["labels"])
    return out


def pick_excerpts(all_rows: dict[str, list[dict]], gold_by_id: dict[str, dict]) -> list[dict]:
    """A few concrete, real failures from the test split for the write-up."""
    wanted = [
        ("consent_or_modal_leak", "cookie_modal"),
        ("related_or_teaser_leak", "news"),
        ("comment_or_signature_leak", "blog_comments"),
        ("empty_output", "recipe"),
        ("empty_output", "non_english"),
        ("over_extraction", "listing"),
        ("script_or_noscript_leak", None),
        ("code_flattened", "docs_code"),
        ("table_lost", None),
    ]
    picked = []
    seen = set()
    for lab, ptype in wanted:
        for name, rows in all_rows.items():
            if name in ("bs4-naive",) and lab != "script_or_noscript_leak":
                continue  # the naive baseline fails by design; prefer real extractors
            hit = next((r for r in rows if r["split"] == "test" and lab in r["labels"]
                        and (ptype is None or r["page_type"] == ptype)), None)
            if hit and (lab, name) not in seen:
                seen.add((lab, name))
                g = gold_by_id[hit["doc_id"]]
                picked.append({
                    "label": lab, "extractor": name, "doc_id": hit["doc_id"],
                    "f1": round(hit["f1"], 3), "precision": round(hit["precision"], 3),
                    "recall": round(hit["recall"], 3),
                    "leaked_snippets": [x["text"] for x in hit["leaked_snippets"]
                                        if taxonomy.KIND_TO_LABEL.get(x["kind"]) == lab][:3],
                    "output_head": hit["output_text"][:400],
                    "gold_head": " ".join(g["main"])[:300],
                })
    return picked


def write_csv(path: Path, all_rows: dict[str, list[dict]]):
    cols = ["extractor", "doc_id", "page_type", "split", "lang", "f1", "precision", "recall", "leak_rate",
            "n_leaked", "n_boilerplate", "table_row_recall", "code_line_recall", "code_line_exact",
            "title_match", "latency_ms", "n_pred_tokens", "n_gold_tokens", "error", "labels"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for name, rows in all_rows.items():
            for r in rows:
                vals = []
                for c in cols:
                    v = name if c == "extractor" else r.get(c)
                    if c == "labels":
                        v = ";".join(r["labels"])
                    elif isinstance(v, float):
                        v = round(v, 4)
                    vals.append("" if v is None else v)
                w.writerow(vals)


def fmt_ci(d: dict) -> str:
    return f"{d['mean']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]"


def fmt(v, nd=2):
    return "n/a" if v is None else f"{v:.{nd}f}"


def results_md(header: dict, summary: list[dict], paired: dict, tax: dict, by_type: dict) -> str:
    L = ["# Results (generated, test split only)", "",
         f"Generated by `python -m extract_bench.run`. Corpus seed {header['corpus_seed']}, "
         f"bootstrap seed {header['bootstrap_seed']}, {header['bootstrap_iters']} resamples, "
         f"n = {header['n_test']} test pages (dev = {header['n_dev']}, used only to tune the best-config row).", "",
         "Library versions: " + ", ".join(f"{k} {v}" for k, v in header["versions"].items()), "",
         f"Python {header['python']} on {header['platform']}.", "",
         "## Main table", "",
         "| Extractor | Config | F1 [95% CI] | Precision | Recall | Boilerplate leak rate | Table rows kept | Code lines kept (exact) | Title match | Median ms |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        L.append(f"| {s['extractor']} | {s['config']} | {fmt_ci(s['f1'])} | {s['precision']['mean']:.3f} | "
                 f"{s['recall']['mean']:.3f} | {s['leak_rate']['mean']:.3f} | {fmt(s['table_row_recall'])} | "
                 f"{fmt(s['code_line_recall'])} ({fmt(s['code_line_exact'])}) | {fmt(s['title_match'])} | "
                 f"{s['latency_ms_median']:.2f} |")
    L += ["", "## Paired comparison of the top two (by mean test F1)", "",
          f"{paired['a']} minus {paired['b']}: mean F1 difference {paired['mean_diff']:+.3f}, "
          f"95% CI [{paired['lo']:+.3f}, {paired['hi']:+.3f}], bootstrap p = {paired['p_value']:.3f}. "
          f"Verdict: **{paired['verdict']}** (resampling single pages)."]
    cl = paired.get("cluster_by_page_type")
    if cl:
        L += ["", "Pages of the same type are built from the same template, so they are not independent. "
              f"Resampling whole page types instead ({cl['n_groups']} groups): {cl['mean_diff']:+.3f}, "
              f"95% CI [{cl['lo']:+.3f}, {cl['hi']:+.3f}], p = {cl['p_value']:.3f}. "
              f"Verdict: **{cl['verdict']}** (resampling page types)."]
    L.append("")
    if paired.get("best_config_vs_default"):
        b = paired["best_config_vs_default"]
        L += [f"Best-config trafilatura minus default trafilatura: {b['mean_diff']:+.3f} "
              f"[{b['lo']:+.3f}, {b['hi']:+.3f}], {b['verdict']}.", ""]
    sv = paired.get("sensitivity_without_listing")
    if sv:
        pt = sv["paired_top_two"]
        L += ["## Sensitivity check: without listing pages", "",
              "The listing-page gold counts only the intro line as content, which is a judgment call. "
              f"Dropping those pages leaves n = {sv['n']}.", "",
              "| Extractor | F1 [95% CI] |", "|---|---|"]
        L += [f"| {r['extractor']} | {fmt_ci(r['f1'])} |" for r in sv["ranking"]]
        L += ["", f"Top two without listing pages: {pt['a']} minus {pt['b']} = {pt['mean_diff']:+.3f} "
              f"[{pt['lo']:+.3f}, {pt['hi']:+.3f}], p = {pt['p_value']:.3f}: **{pt['verdict']}** (resampling pages)."]
        ct = sv.get("paired_top_two_cluster_by_page_type")
        if ct:
            L += ["", f"Resampling page types instead: [{ct['lo']:+.3f}, {ct['hi']:+.3f}], "
                  f"p = {ct['p_value']:.3f}: **{ct['verdict']}**."]
        L.append("")
    L += ["## F1 by page type (mean of 4 test pages each, so treat as rough)", "",
          "| Extractor | " + " | ".join(build_corpus.PAGE_TYPES) + " |",
          "|---|" + "---|" * len(build_corpus.PAGE_TYPES)]
    for name, row in by_type.items():
        L.append(f"| {name} | " + " | ".join(f"{row[t]:.2f}" for t in build_corpus.PAGE_TYPES) + " |")
    L += ["", "## Failure taxonomy (test pages with each label, out of 40)", "",
          "| Extractor | " + " | ".join(taxonomy.LABELS) + " |", "|---|" + "---|" * len(taxonomy.LABELS)]
    for name, counts in tax.items():
        L.append(f"| {name} | " + " | ".join(str(counts.get(lab, 0)) for lab in taxonomy.LABELS) + " |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="1 timing repeat, 2000 bootstrap resamples")
    ap.add_argument("--no-charts", action="store_true")
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--charts-dir", default=None, help="default: charts/ for the default --out, else <out>/charts")
    args = ap.parse_args(argv)
    iters = 2000 if args.quick else stats.DEFAULT_ITERS
    repeats = 1 if args.quick else 3
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.charts_dir:
        charts_dir = Path(args.charts_dir)
    elif out_dir.resolve() == RESULTS.resolve():
        charts_dir = CHARTS
    else:
        charts_dir = out_dir / "charts"  # a custom --out never overwrites the published charts

    if not (build_corpus.CORPUS_DIR / "gold.jsonl").exists():
        build_corpus.write()
    gold = build_corpus.load_gold()
    htmls = {g["doc_id"]: build_corpus.load_html(g["doc_id"]) for g in gold}
    dev = [g for g in gold if g["split"] == "dev"]
    test = [g for g in gold if g["split"] == "test"]
    gold_by_id = {g["doc_id"]: g for g in gold}

    fns = adapters.available()
    unavailable = [s.name for s in adapters.ADAPTERS if s.name not in fns]
    configs = {s.name: s.config for s in adapters.ADAPTERS}
    has_title = {}

    all_rows: dict[str, list[dict]] = {}
    tuning_log = []
    if "trafilatura" in fns:
        best_opts, tuning_log = tune_trafilatura(dev, htmls)
        fns[adapters.BEST_CONFIG_NAME] = tfa.make_configured(**best_opts)
        configs[adapters.BEST_CONFIG_NAME] = "tuned on dev: " + ", ".join(f"{k}={v}" for k, v in best_opts.items())
        (out_dir / "tuning.json").write_text(json.dumps({"grid": tuning_log, "chosen": best_opts}, indent=2))

    for name, fn in fns.items():
        print(f"running {name} ...", flush=True)
        all_rows[name] = evaluate(fn, gold, htmls, repeats)
        has_title[name] = any(r["output_title"] for r in all_rows[name])

    test_rows = {n: [r for r in rows if r["split"] == "test"] for n, rows in all_rows.items()}
    summary = [summarize(n, rows, iters, has_title[n], configs[n]) for n, rows in test_rows.items()]
    summary.sort(key=lambda s: -s["f1"]["mean"])

    # paired test: top two by mean F1 (aligned by doc_id)
    a, b = summary[0]["extractor"], summary[1]["extractor"]
    def f1s(n):
        return [r["f1"] for r in sorted(test_rows[n], key=lambda r: r["doc_id"])]
    def types(n, rows=test_rows):
        return [r["page_type"] for r in sorted(rows[n], key=lambda r: r["doc_id"])]

    paired = {"a": a, "b": b, **stats.paired_bootstrap(f1s(a), f1s(b), iters=iters)}
    # pages of one type share a template, so also resample whole page types
    paired["cluster_by_page_type"] = stats.cluster_paired_bootstrap(f1s(a), f1s(b), types(a), iters=iters)
    paired["all_vs_top"] = {n: stats.paired_bootstrap(f1s(a), f1s(n), iters=iters)
                            for n in test_rows if n != a}
    if adapters.BEST_CONFIG_NAME in test_rows:
        paired["best_config_vs_default"] = stats.paired_bootstrap(
            f1s(adapters.BEST_CONFIG_NAME), f1s("trafilatura"), iters=iters)

    # sensitivity: the listing-page gold ("only the intro counts") is a judgment
    # call, so re-rank without those pages and re-test the top two
    sens_rows = {n: [r for r in rows if r["page_type"] != "listing"] for n, rows in test_rows.items()}
    sens = [{"extractor": n, "f1": stats.bootstrap_ci([r["f1"] for r in rows], iters=iters)}
            for n, rows in sens_rows.items()]
    sens.sort(key=lambda x: -x["f1"]["mean"])
    sa, sb = sens[0]["extractor"], sens[1]["extractor"]

    def sf1(n):
        return [r["f1"] for r in sorted(sens_rows[n], key=lambda r: r["doc_id"])]

    sensitivity = {"excluded_page_types": ["listing"], "n": len(sens_rows[sa]), "ranking": sens,
                   "paired_top_two": {"a": sa, "b": sb, **stats.paired_bootstrap(sf1(sa), sf1(sb), iters=iters)},
                   "paired_top_two_cluster_by_page_type": {
                       "a": sa, "b": sb,
                       **stats.cluster_paired_bootstrap(sf1(sa), sf1(sb), types(sa, sens_rows), iters=iters)}}
    paired["sensitivity_without_listing"] = sensitivity

    tax = {n: dict(Counter(lab for r in rows for lab in r["labels"])) for n, rows in test_rows.items()}
    by_type = {}
    for n in [s["extractor"] for s in summary]:
        d = defaultdict(list)
        for r in test_rows[n]:
            d[r["page_type"]].append(r["f1"])
        by_type[n] = {t: statistics.mean(d[t]) for t in build_corpus.PAGE_TYPES}

    header = {
        "benchmark": "extract-bench",
        "corpus_seed": build_corpus.SEED,
        "bootstrap_seed": stats.DEFAULT_SEED,
        "bootstrap_iters": iters,
        "timing_repeats": repeats,
        "n_dev": len(dev),
        "n_test": len(test),
        "reported_split": "test",
        "versions": adapters.versions(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "unavailable_adapters": unavailable,
    }
    print("versions:", json.dumps(header["versions"]))

    (out_dir / "summary.json").write_text(json.dumps({"header": header, "summary": summary}, indent=2))
    (out_dir / "paired.json").write_text(json.dumps(paired, indent=2))
    (out_dir / "taxonomy.json").write_text(json.dumps({"test_counts": tax, "by_page_type_f1": by_type}, indent=2))
    (out_dir / "excerpts.json").write_text(json.dumps(pick_excerpts(all_rows, gold_by_id), indent=2, ensure_ascii=False))
    write_csv(out_dir / "per_doc.csv", all_rows)
    with open(out_dir / "outputs.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for n, rows in all_rows.items():
            for r in rows:
                f.write(json.dumps({"extractor": n, "doc_id": r["doc_id"], "title": r["output_title"],
                                    "text": r["output_text"]}, ensure_ascii=False) + "\n")
    (out_dir / "RESULTS.md").write_text(results_md(header, summary, paired, tax, by_type), encoding="utf-8")

    if not args.no_charts:
        from . import charts
        charts.make_all(summary, by_type, test_rows, charts_dir)

    print()
    for s in summary:
        print(f"{s['extractor']:28s} F1 {fmt_ci(s['f1'])}  leak {s['leak_rate']['mean']:.3f}  "
              f"median {s['latency_ms_median']:.2f} ms")
    pt = sensitivity["paired_top_two"]
    print(f"without listing: {pt['a']} vs {pt['b']}: diff {pt['mean_diff']:+.3f} "
          f"[{pt['lo']:+.3f}, {pt['hi']:+.3f}] -> {pt['verdict']}")
    print(f"\n{a} vs {b}: diff {paired['mean_diff']:+.3f} [{paired['lo']:+.3f}, {paired['hi']:+.3f}] -> {paired['verdict']}")
    cl = paired["cluster_by_page_type"]
    print(f"  resampling page types: [{cl['lo']:+.3f}, {cl['hi']:+.3f}] -> {cl['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
