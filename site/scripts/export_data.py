"""Export the numbers the site shows, straight from the repo's own result files.

Run from the repo root:  python site/scripts/export_data.py

Writes:
  site/data/site.json         every headline number, slice tables, paired tests, taxonomy, judge stats
  site/data/pages/<id>.json   one file per synthetic test page for the side-by-side viewer
  site/pages/<id>.html        the test page HTML itself (generated corpus, MIT), shown in a sandboxed frame

Nothing is typed in by hand. The viewer re-scores each stored output with
extract_bench.metrics.score and checks the result against results/per_doc.csv,
so the highlighted view and the published table cannot drift apart.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from extract_bench import metrics, stats  # noqa: E402
from extract_bench.judge import kappa_ci  # noqa: E402
from extract_bench.judge_report import pairwise, unanimous_vs_metric  # noqa: E402

RES = ROOT / "results"
OUT = ROOT / "site" / "data"
PAGES_OUT = OUT / "pages"
HTML_OUT = ROOT / "site" / "pages"

ORDER = ["readability-lxml", "trafilatura (best-config)", "trafilatura", "html2text",
         "bs4-naive", "markdownify", "justext"]


def ci(d):
    return {"mean": round(d["mean"], 4), "lo": round(d["lo"], 4), "hi": round(d["hi"], 4)}


def pair(d):
    out = {"diff": round(d["mean_diff"], 4), "lo": round(d["lo"], 4), "hi": round(d["hi"], 4),
           "significant": bool(d["significant"])}
    if "p_value" in d:
        out["p"] = d["p_value"]
    return out


def load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def synthetic():
    s = load("summary.json")
    p = load("paired.json")
    rows = []
    for r in s["summary"]:
        rows.append({
            "extractor": r["extractor"], "config": r["config"],
            "f1": ci(r["f1"]), "precision": round(r["precision"]["mean"], 4),
            "recall": round(r["recall"]["mean"], 4), "leak": round(r["leak_rate"]["mean"], 4),
            "leak_ci": ci(r["leak_rate"]),
            "table_rows": r["table_row_recall"], "code_lines": r["code_line_recall"],
            "code_exact": r["code_line_exact"], "title_match": r["title_match"],
            "latency_ms": round(r["latency_ms_median"], 2),
        })
    extra = {k: v for k, v in s.items() if k not in ("header", "summary")}
    return {"header": s["header"], "rows": rows, "paired_raw": p, "extra_keys": list(extra)}, s, p


def per_doc_csv(name):
    with open(RES / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PAGES_OUT.mkdir(parents=True, exist_ok=True)
    HTML_OUT.mkdir(parents=True, exist_ok=True)

    syn, s_raw, p_raw = synthetic()
    tax = load("taxonomy.json")
    side = load("side_checks.json")
    tuning = load("tuning.json")
    wiki = load("wikipedia.json")
    zyte = load("zyte.json")

    # synthetic per-page rows (test split) for strip plots and per-type means
    syn_docs = [r for r in per_doc_csv("per_doc.csv") if r["split"] == "test"]
    page_types = []
    for r in syn_docs:
        if r["page_type"] not in page_types:
            page_types.append(r["page_type"])
    by_type = {}
    for ex in ORDER:
        by_type[ex] = {}
        for pt in page_types:
            v = [float(r["f1"]) for r in syn_docs if r["extractor"] == ex and r["page_type"] == pt]
            by_type[ex][pt] = round(sum(v) / len(v), 4)

    # sensitivity check without listing pages: recompute with the repo's own bootstrap
    no_listing = {}
    for ex in ORDER:
        v = [float(r["f1"]) for r in syn_docs if r["extractor"] == ex and r["page_type"] != "listing"]
        no_listing[ex] = ci(stats.bootstrap_ci(v, iters=10000, seed=1234)) if hasattr(stats, "bootstrap_ci") else None

    def strip(rows, key="f1"):
        out = {}
        for ex in ORDER:
            out[ex] = [round(float(r[key]), 4) for r in rows if r["extractor"] == ex and r[key] != ""]
        return out

    zyte_rows = per_doc_csv("zyte_per_doc.csv")
    wiki_rows = per_doc_csv("wikipedia_per_doc.csv")

    def slice_rows(summary, site_ci=None):
        out = []
        for r in summary:
            row = {"extractor": r["extractor"], "f1": ci(r["f1"]),
                   "precision": round(r["precision"]["mean"], 4), "recall": round(r["recall"]["mean"], 4),
                   "latency_ms": round(r["latency_ms_median"], 2)}
            if site_ci and r["extractor"] in site_ci:
                row["f1_site"] = ci(site_ci[r["extractor"]])
            out.append(row)
        return out

    def empties(rows):
        out = {}
        for ex in ORDER:
            out[ex] = sum(1 for r in rows if r["extractor"] == ex and int(r["n_pred_tokens"] or 0) == 0)
        return out

    zp = zyte["paired"]
    zyte_paired = {k: {"page": pair(v["page"]), "site": pair(v["site"])} for k, v in zp["vs_top"].items()}
    wp = wiki["paired"]
    wiki_paired = {k: pair(v) for k, v in wp["vs_top"].items()}
    wiki_extra = {k: v for k, v in wp.items() if k not in ("top", "vs_top")}

    # judges
    jq = load("judge_qwen3.8-27b.json")
    jg = load("judge_gpt-oss-120b.json")
    judges = []
    for j in (jq, jg):
        judges.append({"model": j["model"], "n": j["n"], "errors": j["n_errors"],
                       "agreement": round(j["agreement"], 4), "kappa": round(j["cohen_kappa"], 4),
                       "kappa_ci": [round(x, 4) for x in j["cohen_kappa_ci95"]],
                       "metric_good": round(j["metric_good_rate"], 4), "judge_good": round(j["judge_good_rate"], 4),
                       "confusion": j["confusion"], "per_extractor": j["per_extractor"]})
    jj = pairwise(jg, jq)
    una = unanimous_vs_metric([jg, jq])
    recheck = (RES / "judge_recheck_gpt-oss-120b.txt").read_text(encoding="utf-8")
    recheck_lines = [ln.split() for ln in recheck.splitlines() if ln and not ln.startswith("#")]
    recheck_good = sum(1 for ln in recheck_lines if "'GOOD'" in ln)

    site = {
        "synthetic": {
            "header": syn["header"],
            "rows": syn["rows"],
            "top_pair": {"a": p_raw["a"], "b": p_raw["b"], "page": pair(p_raw),
                         "type": pair(p_raw["cluster_by_page_type"])},
            "all_vs_top": {k: pair(v) for k, v in p_raw.get("all_vs_top", {}).items()},
            "paired_other": {k: v for k, v in p_raw.items()
                             if k not in ("a", "b", "mean_diff", "lo", "hi", "n", "p_value", "significant",
                                          "verdict", "cluster_by_page_type", "all_vs_top")},
            "page_types": page_types,
            "by_type": by_type,
            "no_listing": no_listing,
            "strip": strip(syn_docs),
            "taxonomy": tax["test_counts"],
            "n_test": 40,
        },
        "wikipedia": {
            "n_pages": wiki["n_pages"],
            "rows": slice_rows(wiki["summary"]),
            "paired_vs_top": wiki_paired, "top": wp["top"], "paired_extra": wiki_extra,
            "rank": wiki["rank_vs_synthetic"],
            "strip": strip(wiki_rows),
            "empties": empties(wiki_rows),
        },
        "zyte": {
            "n_pages": zyte["n_pages"], "n_sites": zyte["n_sites"],
            "rows": slice_rows(zyte["summary"], zyte["site_ci"]),
            "paired_vs_top": zyte_paired, "top": zp["top"],
            "rank": zyte["rank"],
            "strip": strip(zyte_rows),
            "empties": {ex: zyte["taxonomy_counts"].get(ex, {}).get("empty_output", 0) for ex in ORDER},
            "taxonomy": zyte["taxonomy_counts"],
        },
        "judge": {
            "judges": judges,
            "judge_vs_judge": {"n": jj["n"], "agreement": round(jj["agreement"], 4),
                               "kappa": round(jj["cohen_kappa"], 4),
                               "kappa_ci": [round(x, 4) for x in jj["cohen_kappa_ci95"]]},
            "unanimous": una,
            "recheck": {"n": len(recheck_lines), "flipped_to_good": recheck_good},
        },
        "side_checks": side,
        "tuning": tuning,
    }

    # ---------------- viewer pages ----------------
    gold = {}
    for ln in (ROOT / "corpus" / "gold.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            g = json.loads(ln)
            gold[g["doc_id"]] = g
    outputs = {}
    for ln in (RES / "outputs.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            o = json.loads(ln)
            outputs[(o["extractor"], o["doc_id"])] = o
    csv_idx = {(r["extractor"], r["doc_id"]): r for r in syn_docs}

    N = metrics.LEAK_N
    index = []
    mismatches = 0
    for doc_id, g in gold.items():
        if g["split"] != "test":
            continue
        gold_toks = metrics.tokens("\n".join(g["main"]))
        gold_ng = metrics.ngrams(gold_toks, N)
        snip_ng = []
        for sn in g["boilerplate"]:
            st = metrics.tokens(sn["text"])
            n = min(N, len(st))
            own = metrics.ngrams(st, n) - metrics.ngrams(gold_toks, n) if n else set()
            snip_ng.append((sn["kind"], own, n, st))

        extractors = {}
        for ex in ORDER:
            o = outputs.get((ex, doc_id))
            if o is None:
                continue
            sc = metrics.score(o, g)
            ref = csv_idx[(ex, doc_id)]
            if abs(sc["f1"] - float(ref["f1"])) > 1e-3:
                mismatches += 1
            text = o.get("text") or ""
            out_ng = metrics.ngrams(metrics.remove_title(metrics.tokens(text), metrics.norm_title(g["title"])), N)
            lines = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                lt = metrics.tokens(line)
                if not lt:
                    lines.append({"t": line, "c": "x"})
                    continue
                cls = "x"  # extra: not gold, not a tracked snippet
                if len(lt) < N:
                    if " ".join(lt) in " ".join(gold_toks):
                        cls = "k"
                    else:
                        for kind, own, n, st in snip_ng:
                            if own and metrics.contains_run(st, lt):
                                cls = "l:" + kind
                                break
                else:
                    lng = metrics.ngrams(lt, N)
                    in_gold = len(lng & gold_ng) / len(lng)
                    best_kind, best = None, 0.0
                    for kind, own, n, _st in snip_ng:
                        if n != N or not own:
                            continue
                        f = len(lng & own) / len(lng)
                        if f > best:
                            best_kind, best = kind, f
                    if in_gold >= 0.5 and in_gold >= best:
                        cls = "k"
                    elif best >= 0.3:
                        cls = "l:" + best_kind
                lines.append({"t": line, "c": cls})
            leaked_texts = {x["text"] for x in sc["leaked_snippets"]}
            extractors[ex] = {
                "title": o.get("title"),
                "f1": round(sc["f1"], 4), "precision": round(sc["precision"], 4), "recall": round(sc["recall"], 4),
                "leak": round(sc["leak_rate"], 4), "n_leaked": sc["n_leaked"], "n_boilerplate": sc["n_boilerplate"],
                "labels": [x for x in ref["labels"].split(";") if x],
                "empty": not text.strip(),
                "lines": lines,
                "leaked": [i for i, sn in enumerate(g["boilerplate"]) if sn["text"] in leaked_texts],
                "gold_kept": [],
            }
            # which gold paragraphs survived (half or more of their 4-grams in the output)
            for unit in g["main"]:
                ut = metrics.tokens(unit)
                n = min(N, len(ut))
                ung = metrics.ngrams(ut, n) if n else set()
                on = out_ng if n == N else metrics.ngrams(metrics.tokens(text), n) if n else set()
                extractors[ex]["gold_kept"].append(bool(ung) and len(ung & on) / len(ung) >= 0.5)

        page = {"doc_id": doc_id, "page_type": g["page_type"], "lang": g["lang"], "title": g["title"],
                "main": g["main"], "boilerplate": [{"kind": b["kind"], "text": b["text"]} for b in g["boilerplate"]],
                "extractors": extractors}
        (PAGES_OUT / f"{doc_id}.json").write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8")
        shutil.copyfile(ROOT / "corpus" / "html" / f"{doc_id}.html", HTML_OUT / f"{doc_id}.html")
        index.append({"doc_id": doc_id, "page_type": g["page_type"], "lang": g["lang"], "title": g["title"],
                      "f1": {ex: extractors[ex]["f1"] for ex in extractors}})

    site["viewer_index"] = index
    (OUT / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(index)} viewer pages; score mismatches vs per_doc.csv: {mismatches}")
    if mismatches:
        sys.exit(1)


if __name__ == "__main__":
    main()
