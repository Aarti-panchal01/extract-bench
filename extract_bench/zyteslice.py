"""External-gold slice: the Zyte (ex Scrapinghub) article-extraction-benchmark pages.

    python -m extract_bench.zyteslice build   # download the pinned dataset, write corpus/zyte/manifest.json
    python -m extract_bench.zyteslice run     # score the extractors on it, write results/zyte.*

Why this exists: the synthetic gold and the Wikipedia slice both have weak spots. The synthetic pages and their
gold were written by the repo author. The Wikipedia slice is independent gold but one site template. This slice is
real article pages from many different sites, whose body text was labelled by people at Scrapinghub for their own
benchmark (https://github.com/scrapinghub/article-extraction-benchmark). Nothing here was written or labelled
by this project. No page is selected or dropped by outcome: every page with non-empty gold is used.

Source and licence: the dataset repository is licensed MIT (Copyright (c) 2020 Scrapinghub). The licence covers
their repository; the page HTML and article text inside it were written by the news and blog sites and are not
ours to redistribute. So this repo does NOT commit them. They are downloaded at run time from a pinned commit into
.cache/zyte/ (git-ignored), and corpus/zyte/manifest.json keeps only ids, hosts, URLs, token counts and SHA-256
hashes so a rerun can detect that the data changed.

Gold is the `articleBody` field. The labelled text is plain paragraphs, no headings or captions as such.
Metrics and statistics are the repo's own (metrics.score, stats.*, run.evaluate, run.summarize).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "corpus" / "zyte" / "manifest.json"
CACHE = ROOT / ".cache" / "zyte"
RESULTS = ROOT / "results"

SOURCE_REPO = "https://github.com/scrapinghub/article-extraction-benchmark"
PIN_SHA = "4a3bc979f76c0df73cb95fe272e2fc1b96f9f010"
RAW = "https://raw.githubusercontent.com/scrapinghub/article-extraction-benchmark/" + PIN_SHA + "/"
LICENCE = "MIT, Copyright (c) 2020 Scrapinghub (repo LICENSE and README, checked 23 Oct 2026)"
USER_AGENT = "extract-bench/0.3 (HTML extractor benchmark, research use; https://github.com/Aarti-panchal01)"
MIN_INTERVAL_S = 0.2
DOC_PREFIX = "zyte-"


# ---------------------------------------------------------------- pure helpers

def sha256(b: bytes | str) -> str:
    return hashlib.sha256(b.encode("utf-8") if isinstance(b, str) else b).hexdigest()


def site_of(url: str) -> str:
    """Host without a leading www., lower case. The grouping unit for the site-level bootstrap."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalise_body(text: str) -> list[str]:
    """articleBody -> list of paragraphs: NFC, nbsp and zero-width removed, whitespace collapsed, empty lines dropped."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace(" ", " ")
    for ch in ("​", "‌", "‍", "﻿"):
        text = text.replace(ch, "")
    return [" ".join(line.split()) for line in text.split("\n") if line.strip()]


def gold_record(item_id: str, url: str, paragraphs: list[str]) -> dict:
    """Same record shape as corpus/gold.jsonl so metrics.score and run.evaluate work unchanged."""
    return {"doc_id": f"{DOC_PREFIX}{item_id}", "page_type": site_of(url), "variant": 0, "lang": "en",
            "split": "test", "title": "", "main": paragraphs, "boilerplate": [],
            "table_rows": [], "code_lines": []}


def decode_html(gz_bytes: bytes) -> str:
    return gzip.decompress(gz_bytes).decode("utf-8")


# ---------------------------------------------------------------- network

class Fetcher:
    """Polite binary GET: fixed User-Agent, small gap between requests, retries with backoff."""

    def __init__(self, min_interval: float = MIN_INTERVAL_S, opener: Callable | None = None):
        self.min_interval = min_interval
        self._open = opener or urllib.request.urlopen
        self._last = 0.0
        self.n_requests = 0

    def get(self, url: str, retries: int = 4) -> bytes:
        delay = 2.0
        for attempt in range(retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
            try:
                self.n_requests += 1
                with self._open(req, timeout=60) as r:
                    return r.read()
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                transient = not isinstance(e, urllib.error.HTTPError) or e.code in (429, 500, 502, 503, 504)
                if transient and attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")


def _paths(cache: Path, item_id: str) -> Path:
    return cache / "html" / f"{item_id}.html.gz"


def fetch_all(fetcher: Fetcher, cache: Path = CACHE) -> dict:
    """Download ground-truth.json and every html file listed in it (cached). Returns the ground-truth dict."""
    (cache / "html").mkdir(parents=True, exist_ok=True)
    gt_path = cache / "ground-truth.json"
    if not gt_path.exists():
        gt_path.write_bytes(fetcher.get(RAW + "ground-truth.json"))
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    for item_id in gt:
        p = _paths(cache, item_id)
        if not p.exists():
            p.write_bytes(fetcher.get(RAW + f"html/{item_id}.html.gz"))
    return gt


def build(fetcher: Fetcher, cache: Path = CACHE, manifest: Path = MANIFEST) -> dict:
    gt = fetch_all(fetcher, cache)
    pages, skipped = [], []
    for item_id in sorted(gt):
        item = gt[item_id]
        paragraphs = normalise_body(item.get("articleBody", ""))
        if not paragraphs:
            skipped.append({"id": item_id, "reason": "empty gold"})
            continue
        raw = _paths(cache, item_id).read_bytes()
        html = decode_html(raw)
        pages.append({"id": item_id, "url": item["url"], "site": site_of(item["url"]),
                      "gold_tokens": sum(len(p.split()) for p in paragraphs),
                      "html_gz_sha256": sha256(raw), "html_sha256": sha256(html),
                      "gold_sha256": sha256("\n".join(paragraphs))})
    doc = {"source": SOURCE_REPO, "pinned_commit": PIN_SHA, "licence": LICENCE,
           "rule": "every item in ground-truth.json with non-empty articleBody, in id order; nothing dropped by outcome",
           "n_items_in_source": len(gt), "skipped": skipped, "n_pages": len(pages),
           "n_sites": len({p["site"] for p in pages}), "pages": pages}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(doc, indent=1), encoding="utf-8", newline="\n")
    return doc


def load_slice(manifest: Path = MANIFEST, cache: Path = CACHE, fetcher: Fetcher | None = None,
               verify: bool = True) -> tuple[list[dict], dict[str, str], dict[str, str], list[str]]:
    """Return (gold records, {doc_id: html}, {doc_id: site}, warnings). Missing cache files are downloaded.
    A hash mismatch is a warning, not a failure."""
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    ids = [p["id"] for p in doc["pages"]]
    gt_path = cache / "ground-truth.json"
    need = (not gt_path.exists()) or any(not _paths(cache, i).exists() for i in ids)
    if need:
        if fetcher is None:
            raise FileNotFoundError(f"{cache} is incomplete and no fetcher given; run `build` or pass a Fetcher")
        fetch_all(fetcher, cache)
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    gold, htmls, sites, warnings = [], {}, {}, []
    for p in doc["pages"]:
        raw = _paths(cache, p["id"]).read_bytes()
        html = decode_html(raw)
        paragraphs = normalise_body(gt[p["id"]].get("articleBody", ""))
        if verify:
            if sha256(raw) != p["html_gz_sha256"]:
                warnings.append(f"{p['id'][:12]} ({p['site']}): html hash differs from manifest")
            if sha256("\n".join(paragraphs)) != p["gold_sha256"]:
                warnings.append(f"{p['id'][:12]} ({p['site']}): gold hash differs from manifest")
        rec = gold_record(p["id"], p["url"], paragraphs)
        gold.append(rec)
        htmls[rec["doc_id"]] = html
        sites[rec["doc_id"]] = p["site"]
    return gold, htmls, sites, warnings


# ---------------------------------------------------------------- scoring

def _site_ci(values: list[float], groups: list[str], iters: int, seed: int = 1234) -> dict:
    """95% CI of the mean F1 when whole sites are resampled (page-weighted)."""
    import numpy as np
    v = np.asarray(values, dtype=float)
    names = sorted(set(groups))
    g = np.array([names.index(x) for x in groups])
    sums = np.bincount(g, weights=v, minlength=len(names))
    counts = np.bincount(g, minlength=len(names)).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(names), size=(iters, len(names)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {"mean": float(v.mean()), "lo": float(lo), "hi": float(hi), "n_groups": len(names)}


def run_slice(gold: list[dict], htmls: dict[str, str], sites: dict[str, str], iters: int, repeats: int) -> dict:
    from collections import Counter

    from . import adapters, run, stats
    from .adapters import trafilatura_adapter as tfa
    from .wikislice import spearman

    fns = adapters.available()
    configs = {s.name: s.config for s in adapters.ADAPTERS}
    tuning = json.loads((RESULTS / "tuning.json").read_text(encoding="utf-8"))
    fns[adapters.BEST_CONFIG_NAME] = tfa.make_configured(**tuning["chosen"])
    configs[adapters.BEST_CONFIG_NAME] = ("config tuned on the SYNTHETIC dev split, frozen: "
                                          + ", ".join(f"{k}={v}" for k, v in tuning["chosen"].items()))
    rows = {}
    for name, fn in fns.items():
        print(f"running {name} ...", flush=True)
        rows[name] = run.evaluate(fn, gold, htmls, repeats)
    summary = [run.summarize(n, r, iters, False, configs[n]) for n, r in rows.items()]
    summary.sort(key=lambda s: -s["f1"]["mean"])

    order_ids = sorted(g["doc_id"] for g in gold)
    groups = [sites[d] for d in order_ids]

    def f1s(n):
        return [r["f1"] for r in sorted(rows[n], key=lambda r: r["doc_id"])]

    top = summary[0]["extractor"]
    paired = {"top": top,
              "vs_top": {n: {"page": stats.paired_bootstrap(f1s(top), f1s(n), iters=iters),
                             "site": stats.cluster_paired_bootstrap(f1s(top), f1s(n), groups, iters=iters)}
                         for n in rows if n != top}}
    site_ci = {n: _site_ci(f1s(n), groups, iters) for n in rows}

    synth = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))["summary"]
    synth_f1 = {s["extractor"]: s["f1"]["mean"] for s in synth}
    real_f1 = {s["extractor"]: s["f1"]["mean"] for s in summary}
    wiki_f1 = {}
    wp = RESULTS / "wikipedia.json"
    if wp.exists():
        wiki_f1 = {s["extractor"]: s["f1"]["mean"] for s in json.loads(wp.read_text(encoding="utf-8"))["summary"]}
    common = [n for n in real_f1 if n in synth_f1]
    base = [n for n in common if n != adapters.BEST_CONFIG_NAME]
    rank = {"synthetic_order": sorted(common, key=lambda n: -synth_f1[n]),
            "zyte_order": sorted(common, key=lambda n: -real_f1[n]),
            "spearman_vs_synthetic_7": spearman([synth_f1[n] for n in common], [real_f1[n] for n in common]),
            "spearman_vs_synthetic_6": spearman([synth_f1[n] for n in base], [real_f1[n] for n in base])}
    wcommon = [n for n in base if n in wiki_f1]
    if wcommon:
        rank["wikipedia_order"] = sorted(wiki_f1, key=lambda n: -wiki_f1[n])
        rank["spearman_vs_wikipedia_6"] = spearman([wiki_f1[n] for n in wcommon], [real_f1[n] for n in wcommon])

    tax = {n: dict(Counter(lab for r in rs for lab in r["labels"] if lab != "title_wrong")) for n, rs in rows.items()}
    keep = ("doc_id", "f1", "precision", "recall", "n_pred_tokens", "n_gold_tokens", "latency_ms", "error")
    return {"n_pages": len(gold), "n_sites": len(set(groups)), "bootstrap_iters": iters,
            "bootstrap_seed": stats.DEFAULT_SEED, "timing_repeats": repeats, "versions": adapters.versions(),
            "summary": summary, "site_ci": site_ci, "paired": paired, "rank": rank, "synthetic_f1": synth_f1,
            "wikipedia_f1": wiki_f1, "taxonomy_counts": tax,
            "per_doc": {n: [{k: r[k] for k in keep} for r in rs] for n, rs in rows.items()}}


# ---------------------------------------------------------------- report

SECTION_TITLE = "## External-gold check (Zyte article-extraction-benchmark)"


def _ci(d: dict) -> str:
    return f"{d['mean']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]"


def section_md(res: dict) -> str:
    s = res["summary"]
    rk = res["rank"]
    top = res["paired"]["top"]
    L = [SECTION_TITLE, "",
         f"{res['n_pages']} real article pages from {res['n_sites']} sites. Gold is the human-labelled `articleBody` from "
         f"{SOURCE_REPO} (commit {PIN_SHA[:10]}), so it was written by neither this project nor the tool authors. "
         "Every page with non-empty gold is used, nothing is picked or dropped by outcome. Same metrics code as above, "
         f"{res['bootstrap_iters']} bootstrap resamples, seed {res['bootstrap_seed']}. The page interval resamples pages; "
         "the site interval resamples whole sites, because pages of one site share a template. "
         "Leak rate is not computed (no boilerplate labels). The tuned trafilatura config is the one frozen from the "
         "synthetic dev split, not retuned here.", "",
         "| Extractor | F1 [95% CI, pages] | F1 [95% CI, sites] | Precision | Recall | Empty outputs | Median ms |",
         "|---|---|---|---|---|---|---|"]
    for r in s:
        empty = res["taxonomy_counts"].get(r["extractor"], {}).get("empty_output", 0)
        L.append(f"| {r['extractor']} | {_ci(r['f1'])} | {_ci(res['site_ci'][r['extractor']])} | "
                 f"{r['precision']['mean']:.3f} | {r['recall']['mean']:.3f} | {empty} of {r['n_docs']} | "
                 f"{r['latency_ms_median']:.0f} |")
    L += ["", f"Paired F1 difference, {top} minus each other tool (page resampling, then site resampling):", ""]
    for n, p in res["paired"]["vs_top"].items():
        a, b = p["page"], p["site"]
        L.append(f"- {n}: {a['mean_diff']:+.3f} [{a['lo']:+.3f}, {a['hi']:+.3f}], {a['verdict']}; "
                 f"by site {b['mean_diff']:+.3f} [{b['lo']:+.3f}, {b['hi']:+.3f}], {b['verdict']}")
    L += ["", "How it compares with the other two slices:", "",
          "- Synthetic order (test F1): " + " > ".join(rk["synthetic_order"]),
          "- Zyte order (F1): " + " > ".join(rk["zyte_order"])]
    if "wikipedia_order" in rk:
        L.append("- Wikipedia order (F1): " + " > ".join(rk["wikipedia_order"]))
    L.append(f"- Spearman against synthetic: {rk['spearman_vs_synthetic_6']:.2f} over the 6 default-config tools, "
             f"{rk['spearman_vs_synthetic_7']:.2f} over 7 rows.")
    if "spearman_vs_wikipedia_6" in rk:
        L.append(f"- Spearman against Wikipedia: {rk['spearman_vs_wikipedia_6']:.2f} over the 6 default-config tools.")
    L += ["", "Caveats specific to this slice:", "",
          "- News and blog article pages only, so it says little about recipes, forums, listings or documentation. "
          "Pages were fetched with JavaScript off.",
          "- The labelled body is plain paragraphs. Tools that keep headings, captions, bylines or link lists lose a "
          "little precision although some of that text is arguably content. Recall is the fairer column for them.",
          "- The dataset's own README publishes results for trafilatura, readability and jusText on these pages, so "
          "the tool authors could have tuned against it. This slice is not blind to them.",
          "- Page HTML and gold text are not in git. `corpus/zyte/manifest.json` has ids, URLs, token counts and "
          "SHA-256 hashes; `python -m extract_bench.zyteslice run` downloads the pinned commit and checks them. "
          f"Source licence: {LICENCE}.", ""]
    return "\n".join(L)


def splice_into_results(results_md: Path, section: str) -> None:
    text = results_md.read_text(encoding="utf-8") if results_md.exists() else ""
    if SECTION_TITLE in text:
        start = text.index(SECTION_TITLE)
        nxt = text.find("\n## ", start + 1)
        tail = text[nxt + 1:] if nxt != -1 else ""
        text = text[:start] + section + ("\n" + tail if tail else "")
        results_md.write_text(text, encoding="utf-8", newline="\n")
        return
    text = text.rstrip("\n") + "\n\n" if text else ""
    results_md.write_text(text + section, encoding="utf-8", newline="\n")


def write_per_doc_csv(path: Path, per_doc: dict, sites: dict[str, str]) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["extractor", "doc_id", "site", "f1", "precision", "recall", "n_pred_tokens", "n_gold_tokens",
                    "latency_ms", "error"])
        for n, rs in per_doc.items():
            for r in rs:
                w.writerow([n, r["doc_id"], sites[r["doc_id"]], round(r["f1"], 4), round(r["precision"], 4),
                            round(r["recall"], 4), r["n_pred_tokens"], r["n_gold_tokens"],
                            round(r["latency_ms"], 2), r["error"] or ""])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "run"])
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.cmd == "build":
        doc = build(Fetcher())
        print(f"wrote {MANIFEST}: {doc['n_pages']} pages, {doc['n_sites']} sites, skipped {doc['skipped']}")
        return 0
    iters = 2000 if args.quick else 10_000
    repeats = 1 if args.quick else 3
    gold, htmls, sites, warns = load_slice(fetcher=Fetcher())
    for w in warns:
        print("WARNING:", w)
    res = run_slice(gold, htmls, sites, iters, repeats)
    res["warnings"] = warns
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "zyte.json").write_text(json.dumps(res, indent=2), encoding="utf-8", newline="\n")
    write_per_doc_csv(out / "zyte_per_doc.csv", res["per_doc"], sites)
    splice_into_results(out / "RESULTS.md", section_md(res))
    for s in res["summary"]:
        print(f"{s['extractor']:28s} F1 {_ci(s['f1'])}  site {_ci(res['site_ci'][s['extractor']])}  "
              f"P {s['precision']['mean']:.3f} R {s['recall']['mean']:.3f}")
    print(json.dumps(res["rank"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
