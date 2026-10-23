"""Real-page slice: English Wikipedia articles with gold text from the Wikipedia API.

    python -m extract_bench.wikislice build   # select 40 articles by the fixed rule, fetch + cache, write the manifest
    python -m extract_bench.wikislice run     # score the extractors on the cached slice, write results/wikipedia.*

Why this exists: the 60 synthetic pages and their gold are both written by the
repo author. Here the page HTML is a real rendered Wikipedia article (nav,
sidebar, footer, reference list, navboxes all present) and the gold is the
MediaWiki plain-text extract of the same revision, which nobody on this project
wrote.

Selection rule (fixed before any extractor was run):
1. rng = random.Random(SEED); draw page ids uniformly from 1..MAX_PAGEID in
   order, 50 at a time, skipping repeats.
2. Keep a page only if it is in the main namespace, is not a redirect, is not a
   disambiguation page, and its wikitext is between MIN_BYTES and MAX_BYTES.
3. Fetch its plain-text extract; normalise it (see normalise_extract); keep the
   page only if the normalised gold has at least MIN_GOLD_TOKENS tokens and the
   page revision did not change between the info call and the extract call.
4. Stop at N_PAGES kept pages. The kept pages, in draw order, are the slice.

Licensing: Wikipedia text is CC BY-SA 4.0. The fetched HTML and the gold text
are NOT committed (cache dir is git-ignored). The repo keeps only
corpus/wikipedia/manifest.json: titles, page ids, revision ids, SHA-256 hashes
and the rule above, so anyone can refetch the exact revisions
(https://en.wikipedia.org/w/index.php?oldid=<revid>) and check the hashes.

Metrics and statistics are the repo's own (metrics.score, stats.*, run.evaluate,
run.summarize); nothing is re-implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "corpus" / "wikipedia" / "manifest.json"
CACHE = ROOT / ".cache" / "wikipedia"
RESULTS = ROOT / "results"

API = "https://en.wikipedia.org/w/api.php"
ARTICLE_BY_REV = "https://en.wikipedia.org/w/index.php?oldid={revid}"
USER_AGENT = ("extract-bench/0.2 (HTML extractor benchmark, research use, polite single-threaded client; "
              "https://github.com/Aarti-panchal01)")
MIN_INTERVAL_S = 1.0

SEED = 20261023
N_PAGES = 40
MAX_PAGEID = 80_000_000
ID_BATCH = 50
MIN_BYTES = 20_000
MAX_BYTES = 150_000
MIN_GOLD_TOKENS = 800

# Trailing sections whose content is link lists or footnotes, not article prose.
DROP_SECTIONS = {"see also", "notes", "references", "further reading", "external links", "bibliography",
                 "sources", "footnotes", "citations", "notes and references"}

DOC_PREFIX = "wiki-"


# ---------------------------------------------------------------- pure helpers

def sample_ids(seed: int, count: int, max_id: int = MAX_PAGEID) -> list[int]:
    """Deterministic page ids: the first `count` distinct draws of Random(seed).
    Asking for a longer list returns the same prefix."""
    rng = random.Random(seed)
    out: list[int] = []
    have: set[int] = set()
    while len(out) < count:
        i = rng.randint(1, max_id)
        if i not in have:
            have.add(i)
            out.append(i)
    return out


def candidate_ok(page: dict) -> bool:
    """Step 2 of the rule, on one page object of an action=query&prop=info|pageprops reply."""
    if page.get("missing") or page.get("invalid"):
        return False
    if page.get("ns") != 0 or page.get("redirect"):
        return False
    if "disambiguation" in (page.get("pageprops") or {}):
        return False
    return MIN_BYTES <= int(page.get("length", 0)) <= MAX_BYTES


def _heading(line: str) -> tuple[int, str] | None:
    s = line.strip()
    if len(s) > 4 and s.startswith("==") and s.endswith("=="):
        level = min(len(s) - len(s.lstrip("=")), len(s) - len(s.rstrip("=")))
        return level, s.strip("=").strip()
    return None


def normalise_extract(text: str, drop_sections: bool = True) -> list[str]:
    """MediaWiki explaintext extract -> list of paragraph strings (the gold 'main').

    - Unicode NFC; no-break space to plain space; zero-width characters removed
    - '== Heading ==' markers become the plain heading text (headings are visible text on the page)
    - sections named in DROP_SECTIONS are removed, up to the next heading of the same or a higher level
      (skipped when drop_sections=False, used only by the back-matter sensitivity variant)
    - whitespace inside a line is collapsed, empty lines dropped; one non-empty line = one paragraph
    """
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    out: list[str] = []
    skip_level: int | None = None
    for raw in text.splitlines():
        h = _heading(raw)
        if h:
            level, name = h
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if drop_sections and skip_level is None and name.lower() in DROP_SECTIONS:
                skip_level = level
                continue
            if skip_level is None and name:
                out.append(" ".join(name.split()))
            continue
        if skip_level is not None:
            continue
        line = " ".join(raw.split())
        if line:
            out.append(line)
    return out


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def gold_record(title: str, pageid: int, paragraphs: list[str]) -> dict:
    """Same record shape as corpus/gold.jsonl so metrics.score and run.evaluate work unchanged."""
    return {"doc_id": f"{DOC_PREFIX}{pageid}", "page_type": "wikipedia", "variant": 0, "lang": "en",
            "split": "test", "title": title, "main": paragraphs, "boilerplate": [],
            "table_rows": [], "code_lines": []}


# ---------------------------------------------------------------- network

class Client:
    """Polite HTTP client: fixed User-Agent, at most one request per MIN_INTERVAL_S, retries on 429/5xx."""

    def __init__(self, min_interval: float = MIN_INTERVAL_S, opener: Callable | None = None):
        self.min_interval = min_interval
        self._last = 0.0
        self._open = opener or urllib.request.urlopen
        self.n_requests = 0

    def get(self, url: str, retries: int = 4) -> str:
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
                    return r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")

    def api(self, **params) -> dict:
        params.update(format="json", formatversion="2", maxlag="5")
        return json.loads(self.get(API + "?" + urllib.parse.urlencode(params)))


def fetch_info(client: Client, ids: list[int]) -> list[dict]:
    r = client.api(action="query", pageids="|".join(map(str, ids)), prop="info|pageprops", ppprop="disambiguation")
    by_id = {p["pageid"]: p for p in r.get("query", {}).get("pages", []) if "pageid" in p}
    return [by_id[i] for i in ids if i in by_id]  # keep draw order


def fetch_extract(client: Client, pageid: int) -> dict:
    r = client.api(action="query", pageids=str(pageid), prop="extracts|info", explaintext="1", exsectionformat="wiki")
    p = r["query"]["pages"][0]
    return {"title": p["title"], "extract": p.get("extract", ""), "lastrevid": p["lastrevid"]}


def fetch_html(client: Client, revid: int) -> str:
    return client.get(ARTICLE_BY_REV.format(revid=revid))


def _cache_paths(cache: Path, revid: int) -> tuple[Path, Path]:
    return cache / f"{revid}.html", cache / f"{revid}.gold.txt"


def _raw_path(cache: Path, revid: int) -> Path:
    return cache / f"{revid}.extract.txt"


def build(client: Client, cache: Path = CACHE, manifest: Path = MANIFEST, n_pages: int = N_PAGES,
          log: Callable[[str], None] = print) -> dict:
    """Apply the selection rule, fetch and cache HTML + gold, write the manifest."""
    from .metrics import tokens

    cache.mkdir(parents=True, exist_ok=True)
    kept: list[dict] = []
    skipped = {"filtered_by_info": 0, "gold_too_short": 0, "revision_changed": 0}
    drawn = 0
    batch_no = 0
    while len(kept) < n_pages:
        ids = sample_ids(SEED, (batch_no + 1) * ID_BATCH)[batch_no * ID_BATCH:]
        batch_no += 1
        drawn += len(ids)
        for page in fetch_info(client, ids):
            if len(kept) >= n_pages:
                break
            if not candidate_ok(page):
                skipped["filtered_by_info"] += 1
                continue
            ex = fetch_extract(client, page["pageid"])
            if ex["lastrevid"] != page["lastrevid"]:
                skipped["revision_changed"] += 1
                continue
            paragraphs = normalise_extract(ex["extract"])
            gold_text = "\n".join(paragraphs)
            if len(tokens(gold_text)) < MIN_GOLD_TOKENS:
                skipped["gold_too_short"] += 1
                continue
            hp, gp = _cache_paths(cache, ex["lastrevid"])
            _raw_path(cache, ex["lastrevid"]).write_text(ex["extract"], encoding="utf-8", newline="\n")
            html = hp.read_text(encoding="utf-8") if hp.exists() else fetch_html(client, ex["lastrevid"])  # cache hit: no request
            hp.write_text(html, encoding="utf-8", newline="\n")
            gp.write_text(gold_text, encoding="utf-8", newline="\n")
            kept.append({"pageid": page["pageid"], "title": ex["title"], "revid": ex["lastrevid"],
                         "wikitext_bytes": page["length"], "html_sha256": sha256(html),
                         "gold_sha256": sha256(gold_text), "extract_sha256": sha256(ex["extract"]),
                         "n_gold_tokens": len(tokens(gold_text))})
            log(f"  kept {len(kept):2d}/{n_pages}: {ex['title']} (rev {ex['lastrevid']}, {len(html) // 1024} KB html)")
        log(f"  drawn {drawn} ids so far, requests {client.n_requests}")
    doc = {
        "about": "Wikipedia real-page slice for extract-bench. HTML and gold text are not stored in git "
                 "(CC BY-SA 4.0); refetch with `python -m extract_bench.wikislice build` or from the permalinks.",
        "rule": {"seed": SEED, "id_range": [1, MAX_PAGEID], "id_batch": ID_BATCH, "namespace": 0,
                 "skip": ["redirects", "disambiguation pages"], "wikitext_bytes": [MIN_BYTES, MAX_BYTES],
                 "min_gold_tokens": MIN_GOLD_TOKENS, "n_pages": n_pages,
                 "dropped_gold_sections": sorted(DROP_SECTIONS)},
        "html_source": "https://en.wikipedia.org/w/index.php?oldid=<revid> (normal article render)",
        "gold_source": "action=query&prop=extracts&explaintext=1 for the same revision, then normalise_extract()",
        "licence": "Wikipedia text: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/ ; authors: see each page history",
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "ids_drawn": drawn, "skipped": skipped,
        "pages": [dict(p, permalink=ARTICLE_BY_REV.format(revid=p["revid"])) for p in kept],
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return doc


def load_slice(manifest: Path = MANIFEST, cache: Path = CACHE, client: Client | None = None,
               verify: bool = True, keep_back_matter: bool = False) -> tuple[list[dict], dict[str, str], list[str]]:
    """Return (gold records, {doc_id: html}, warnings). Missing cache files are refetched by revision id.
    A hash mismatch is reported in warnings (Wikipedia can re-render an old revision after a template change).
    keep_back_matter=True builds the sensitivity gold: same extract, but See also / Bibliography / External links
    sections are kept (footnote lists are never in the API extract)."""
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    cache.mkdir(parents=True, exist_ok=True)
    gold, htmls, warnings = [], {}, []
    for p in doc["pages"]:
        hp, gp = _cache_paths(cache, p["revid"])
        if not hp.exists():
            if client is None:
                raise FileNotFoundError(f"{hp} missing and no client given; run `build` or pass a Client")
            hp.write_text(fetch_html(client, p["revid"]), encoding="utf-8", newline="\n")
        if not gp.exists():
            if client is None:
                raise FileNotFoundError(f"{gp} missing and no client given")
            ex = fetch_extract(client, p["pageid"])
            if ex["lastrevid"] != p["revid"]:
                warnings.append(f"{p['title']}: current revision {ex['lastrevid']} differs from pinned {p['revid']}; "
                                "gold is from the newer revision")
            gp.write_text("\n".join(normalise_extract(ex["extract"])), encoding="utf-8", newline="\n")
        html = hp.read_text(encoding="utf-8")
        gold_text = gp.read_text(encoding="utf-8")
        if verify:
            if sha256(html) != p["html_sha256"]:
                warnings.append(f"{p['title']}: html hash differs from manifest")
            if sha256(gold_text) != p["gold_sha256"]:
                warnings.append(f"{p['title']}: gold hash differs from manifest")
        if keep_back_matter:
            rp = _raw_path(cache, p["revid"])
            if not rp.exists():
                if client is None:
                    raise FileNotFoundError(f"{rp} missing and no client given")
                ex = fetch_extract(client, p["pageid"])
                if ex["lastrevid"] != p["revid"]:
                    warnings.append(f"{p['title']}: current revision {ex['lastrevid']} differs from pinned {p['revid']}")
                rp.write_text(ex["extract"], encoding="utf-8", newline="\n")
            raw = rp.read_text(encoding="utf-8")
            if verify and p.get("extract_sha256") and sha256(raw) != p["extract_sha256"]:
                warnings.append(f"{p['title']}: raw extract hash differs from manifest")
            paragraphs = normalise_extract(raw, drop_sections=False)
        else:
            paragraphs = gold_text.split("\n")
        rec = gold_record(p["title"], p["pageid"], paragraphs)
        gold.append(rec)
        htmls[rec["doc_id"]] = html
    return gold, htmls, warnings


# ---------------------------------------------------------------- scoring

def _ranks(values: list[float]) -> list[float]:
    """Average ranks, 1 = highest value."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    import numpy as np
    ra, rb = np.array(_ranks(a)), np.array(_ranks(b))
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def run_slice(gold: list[dict], htmls: dict[str, str], iters: int, repeats: int,
              gold_back_matter: list[dict] | None = None) -> dict:
    from collections import Counter

    from . import adapters, run, stats
    from .adapters import trafilatura_adapter as tfa

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
    summary = [run.summarize(n, r, iters, any(x["output_title"] for x in r), configs[n]) for n, r in rows.items()]
    summary.sort(key=lambda s: -s["f1"]["mean"])

    def f1s(n):
        return [r["f1"] for r in sorted(rows[n], key=lambda r: r["doc_id"])]

    top = summary[0]["extractor"]
    paired = {"top": top, "vs_top": {n: stats.paired_bootstrap(f1s(top), f1s(n), iters=iters)
                                     for n in rows if n != top}}
    r_name, t_name = "readability-lxml", adapters.BEST_CONFIG_NAME
    if r_name in rows and t_name in rows:
        # the top pair on the synthetic corpus, reported here whatever the order is
        paired["readability_minus_trafilatura_best"] = {
            "a": r_name, "b": t_name, **stats.paired_bootstrap(f1s(r_name), f1s(t_name), iters=iters)}

    synth = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))["summary"]
    synth_f1 = {s["extractor"]: s["f1"]["mean"] for s in synth}
    real_f1 = {s["extractor"]: s["f1"]["mean"] for s in summary}
    common = [n for n in real_f1 if n in synth_f1]
    base = [n for n in common if n != adapters.BEST_CONFIG_NAME]
    rank = {"synthetic_order": sorted(common, key=lambda n: -synth_f1[n]),
            "real_order": sorted(common, key=lambda n: -real_f1[n]),
            "spearman_all_7": spearman([synth_f1[n] for n in common], [real_f1[n] for n in common]),
            "spearman_base_6": spearman([synth_f1[n] for n in base], [real_f1[n] for n in base])}

    variant = None
    if gold_back_matter is not None:
        vrows = {n: run.evaluate(fn, gold_back_matter, htmls, 1) for n, fn in fns.items()}
        vsum = sorted(({"extractor": n, "f1": stats.bootstrap_ci([r["f1"] for r in rs], iters=iters),
                        "precision": stats.bootstrap_ci([r["precision"] for r in rs], iters=iters),
                        "recall": stats.bootstrap_ci([r["recall"] for r in rs], iters=iters)}
                       for n, rs in vrows.items()), key=lambda x: -x["f1"]["mean"])
        vf = {x["extractor"]: x["f1"]["mean"] for x in vsum}
        vcommon = [n for n in vf if n in synth_f1]
        vbase = [n for n in vcommon if n != adapters.BEST_CONFIG_NAME]
        variant = {"summary": vsum, "order": [x["extractor"] for x in vsum],
                   "spearman_all_7": spearman([synth_f1[n] for n in vcommon], [vf[n] for n in vcommon]),
                   "spearman_base_6": spearman([synth_f1[n] for n in vbase], [vf[n] for n in vbase])}

    tax = {n: dict(Counter(lab for r in rs for lab in r["labels"] if lab != "title_wrong")) for n, rs in rows.items()}
    keep = ("doc_id", "f1", "precision", "recall", "n_pred_tokens", "n_gold_tokens", "latency_ms", "error")
    return {"n_pages": len(gold), "bootstrap_iters": iters, "bootstrap_seed": stats.DEFAULT_SEED,
            "timing_repeats": repeats, "versions": adapters.versions(), "summary": summary, "paired": paired,
            "rank_vs_synthetic": rank, "back_matter_variant": variant, "synthetic_f1": synth_f1, "taxonomy_counts": tax,
            "per_doc": {n: [{k: r[k] for k in keep} for r in rs] for n, rs in rows.items()}}


# ---------------------------------------------------------------- report

SECTION_TITLE = "## Real-page check (Wikipedia)"


def _ci(d: dict) -> str:
    return f"{d['mean']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]"


def section_md(res: dict) -> str:
    s = res["summary"]
    rk = res["rank_vs_synthetic"]
    top = res["paired"]["top"]
    L = [SECTION_TITLE, "",
         f"{res['n_pages']} real English Wikipedia articles, rendered page HTML (nav, sidebar, footer, references and "
         "navboxes all present). Gold is the MediaWiki plain-text extract of the same revision, normalised "
         "(`extract_bench/wikislice.py`), so the gold was not written by the benchmark author. Pages were drawn "
         f"by a seeded random draw over page ids (seed {SEED}, rule in the module docstring), fixed before any tool ran. "
         f"Same metrics code as above, {res['bootstrap_iters']} bootstrap resamples, page-level 95% intervals. "
         "Leak rate is not computed here (this gold has no boilerplate labels). Wikipedia is one site template, so "
         "the page-type cluster test does not apply; the intervals cover page-to-page variation within one template only.",
         "",
         "| Extractor | F1 [95% CI] | Precision | Recall | Empty outputs | Median ms |", "|---|---|---|---|---|---|"]
    for r in s:
        empty = res["taxonomy_counts"].get(r["extractor"], {}).get("empty_output", 0)
        L.append(f"| {r['extractor']} | {_ci(r['f1'])} | {r['precision']['mean']:.3f} | {r['recall']['mean']:.3f} | "
                 f"{empty} of {r['n_docs']} | {r['latency_ms_median']:.0f} |")
    L += ["", "Paired F1 difference against the top tool on real pages (resampling pages):", ""]
    for n, p in res["paired"]["vs_top"].items():
        L.append(f"- {top} minus {n}: {p['mean_diff']:+.3f} [{p['lo']:+.3f}, {p['hi']:+.3f}], {p['verdict']}")
    rt = res["paired"].get("readability_minus_trafilatura_best")
    if rt:
        L += ["", f"The synthetic top pair, {rt['a']} minus {rt['b']}: {rt['mean_diff']:+.3f} "
              f"[{rt['lo']:+.3f}, {rt['hi']:+.3f}], {rt['verdict']}."]
    L += ["", "Does the synthetic ranking hold?", "",
          "- Synthetic order (test F1): " + " > ".join(rk["synthetic_order"]),
          "- Wikipedia order (F1): " + " > ".join(rk["real_order"]),
          f"- Spearman rank correlation: {rk['spearman_all_7']:.2f} over all 7 rows, "
          f"{rk['spearman_base_6']:.2f} over the 6 default-config tools. With 6 to 7 tools, treat it as a rough signal.",
          ""]
    bm = res.get("back_matter_variant")
    if bm:
        L += ["Sensitivity check, added after the first run: back matter kept in the gold. The primary gold removes "
              "See also, Notes, References, Further reading, External links, Bibliography and Sources. Tools that keep "
              "those lists (most do) were therefore charged in precision. The variant keeps the same API extract but "
              "does not remove those sections (footnote lists are never in the API extract). It was chosen after seeing "
              "the primary result, so it is a check on one design decision, not a second headline.", "",
              "| Extractor | F1 [95% CI], back matter kept | Precision | Recall |", "|---|---|---|---|"]
        for r in bm["summary"]:
            L.append(f"| {r['extractor']} | {_ci(r['f1'])} | {r['precision']['mean']:.3f} | {r['recall']['mean']:.3f} |")
        L += ["", "- Order with back matter kept: " + " > ".join(bm["order"]),
              f"- Spearman against the synthetic order: {bm['spearman_all_7']:.2f} over 7 rows, "
              f"{bm['spearman_base_6']:.2f} over the 6 default-config tools.", ""]
    L += ["Caveats specific to this slice:", "",
          "- One site template. Wikipedia pages share a skin, so this tests extraction on one real template at many "
          "article lengths, not on varied real-world layouts.",
          "- The extract gold keeps prose and headings only. It drops infobox text, table cells and captions, and the "
          "reference and see-also lists were removed by the normaliser. A tool that keeps tables, infobox or reference "
          "text loses precision here although that text is arguably content. Recall is the fairer column for those tools.",
          "- Inline citation markers such as [12] are in the HTML but not in the gold, a small precision cost for every tool.",
          "- 40 pages is small. The slice is a check on direction, not a second benchmark.",
          "- HTML and gold text are not in git (CC BY-SA 4.0). `corpus/wikipedia/manifest.json` has page ids, revision "
          "permalinks and SHA-256 hashes; `python -m extract_bench.wikislice build` redraws the pages and "
          "`run` refetches the pinned revisions and re-scores them. Text: Wikipedia contributors, CC BY-SA 4.0.", ""]
    return "\n".join(L)


def splice_into_results(results_md: Path, section: str) -> None:
    text = results_md.read_text(encoding="utf-8") if results_md.exists() else ""
    if SECTION_TITLE in text:
        text = text[:text.index(SECTION_TITLE)].rstrip("\n") + "\n\n"
    elif text:
        text = text.rstrip("\n") + "\n\n"
    results_md.write_text(text + section, encoding="utf-8", newline="\n")


def write_per_doc_csv(path: Path, per_doc: dict) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["extractor", "doc_id", "f1", "precision", "recall", "n_pred_tokens", "n_gold_tokens",
                    "latency_ms", "error"])
        for n, rs in per_doc.items():
            for r in rs:
                w.writerow([n, r["doc_id"], round(r["f1"], 4), round(r["precision"], 4), round(r["recall"], 4),
                            r["n_pred_tokens"], r["n_gold_tokens"], round(r["latency_ms"], 2), r["error"] or ""])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "run"])
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # article titles are not all cp1252
    if args.cmd == "build":
        doc = build(Client())
        print(f"wrote {MANIFEST} with {len(doc['pages'])} pages; skipped {doc['skipped']}")
        return 0
    iters = 2000 if args.quick else 10_000
    repeats = 1 if args.quick else 3
    client = Client()
    gold, htmls, warns = load_slice(client=client)
    gold_bm, _, warns2 = load_slice(client=client, keep_back_matter=True)
    warns = warns + warns2
    for w in warns:
        print("WARNING:", w)
    res = run_slice(gold, htmls, iters, repeats, gold_back_matter=gold_bm)
    res["warnings"] = warns
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "wikipedia.json").write_text(json.dumps(res, indent=2), encoding="utf-8", newline="\n")
    write_per_doc_csv(out / "wikipedia_per_doc.csv", res["per_doc"])
    splice_into_results(out / "RESULTS.md", section_md(res))
    for s in res["summary"]:
        print(f"{s['extractor']:28s} F1 {_ci(s['f1'])}  P {s['precision']['mean']:.3f} R {s['recall']['mean']:.3f}")
    print(json.dumps(res["rank_vs_synthetic"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
