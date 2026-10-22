"""Optional LLM judge, used only to measure how well the token metric agrees
with a model's opinion. It is never part of the main ranking.

    python -m extract_bench.judge                 # skipped unless a key is set
    python -m extract_bench.judge --mock          # offline stand-in judge (pipeline check only)
    GROQ_API_KEY=... python -m extract_bench.judge --n 60
    GROQ_API_KEY=... JUDGE_MODEL=qwen/qwen3.8-27b python -m extract_bench.judge --per-extractor 20 --out-name judge_qwen3.8-27b.json
    ANTHROPIC_API_KEY=... python -m extract_bench.judge --n 60

The metric label for a page is GOOD when F1 >= 0.8 and leak rate <= 0.2.
The judge sees the gold content and the extractor output and answers GOOD or
BAD. Agreement is reported as Cohen's kappa. Results go to results/judge.json unless --out-name is given.
Model names can be changed with JUDGE_MODEL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import build_corpus, stats

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
# Longest output in the published run is about 5,100 characters, so nothing is cut.
MAX_CHARS = 8000

PROMPT = """You are grading a web page text extractor.

GOLD = the true main content of the page.
OUTPUT = what the extractor returned.

Answer GOOD if OUTPUT contains nearly all of GOLD and very little extra text
(menus, cookie notices, comments, related links, ads). Otherwise answer BAD.
Reply with exactly one word: GOOD or BAD.

GOLD:
{gold}

OUTPUT:
{output}
"""


def metric_label(row: dict) -> str:
    return "GOOD" if float(row["f1"]) >= 0.8 and float(row["leak_rate"]) <= 0.2 else "BAD"


def parse_verdict(text: str) -> str:
    """Read the model's one-word answer. "NOT GOOD" counts as BAD; anything unclear is BAD."""
    words = re.findall(r"[A-Z]+", (text or "").upper())
    if words[:2] == ["NOT", "GOOD"]:
        return "BAD"
    for w in words:
        if w in ("GOOD", "BAD"):
            return w
    return "BAD"


def mock_judge(gold: str, output: str) -> str:
    """Offline stand-in: a crude length-ratio rule. Exists so the pipeline can be
    tested without a key. Its kappa says nothing about real LLM judges."""
    g, o = len(gold.split()), len(output.split())
    return "GOOD" if g and 0.8 <= o / g <= 1.3 else "BAD"


def _post(url: str, headers: dict, body: dict, retries: int = 6) -> dict:
    """POST JSON. Rate limits (429) and server errors (5xx) are retried with backoff."""
    for attempt in range(retries + 1):
        # Some API edges block the default urllib User-Agent (Cloudflare error 1010).
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"User-Agent": "extract-bench/0.1", **headers}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310 - fixed https endpoints
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if attempt == retries or not (e.code == 429 or e.code >= 500):
                raise
            wait = float(e.headers.get("retry-after") or 0) or min(60.0, 2.0 ** (attempt + 1))
            time.sleep(min(wait, 90.0))
    raise RuntimeError("unreachable")


GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"


def groq_body(model: str, prompt: str) -> dict:
    """Request body for Groq. Reasoning models need room to think before the one-word
    answer, so max_tokens is not 3; their reasoning is kept short or hidden."""
    body = {"model": model, "temperature": 0, "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}]}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    elif model.startswith("qwen/"):
        body["reasoning_effort"] = "none"
    return body


def groq_judge(gold: str, output: str) -> str:
    body = groq_body(os.environ.get("JUDGE_MODEL", GROQ_DEFAULT_MODEL), PROMPT.format(gold=gold, output=output))
    data = _post("https://api.groq.com/openai/v1/chat/completions",
                 {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json"}, body)
    return parse_verdict(data["choices"][0]["message"]["content"])


def anthropic_judge(gold: str, output: str) -> str:
    body = {"model": os.environ.get("JUDGE_MODEL", "claude-haiku-4-5"), "max_tokens": 5,
            "messages": [{"role": "user", "content": PROMPT.format(gold=gold, output=output)}]}
    data = _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                  "content-type": "application/json"}, body)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    return parse_verdict(text)


def pick_judge(mock: bool):
    if mock:
        return "mock", mock_judge
    if os.environ.get("GROQ_API_KEY"):
        return "groq", groq_judge
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", anthropic_judge
    return None, None


def stratified_sample(rows: list[dict], per_extractor: int, seed: int) -> list[dict]:
    """Same number of pages for every extractor, so no tool dominates the agreement."""
    rng = random.Random(seed)
    by_ext: dict[str, list[dict]] = {}
    for r in rows:
        by_ext.setdefault(r["extractor"], []).append(r)
    out = []
    for ext in sorted(by_ext):
        group = sorted(by_ext[ext], key=lambda r: r["doc_id"])
        out.extend(rng.sample(group, min(per_extractor, len(group))))
    return out


def kappa_ci(a: list[str], b: list[str], iters: int = 2000, seed: int = 7) -> list[float] | None:
    """Percentile bootstrap CI for Cohen's kappa (resampling items)."""
    if len(a) < 2:
        return None
    rng = random.Random(seed)
    idx = range(len(a))
    vals = []
    for _ in range(iters):
        pick = [rng.choice(idx) for _ in idx]
        k = stats.cohen_kappa([a[i] for i in pick], [b[i] for i in pick])
        if k == k:  # skip NaN when a resample has one label only
            vals.append(k)
    if not vals:
        return None
    vals.sort()
    return [vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]]


def summarize(items: list[dict]) -> dict:
    """Agreement, kappa with CI, the 2x2 table and agreement per extractor."""
    m = [i["metric"] for i in items]
    j = [i["judge"] for i in items]
    confusion = {f"metric_{a}_judge_{b}": sum(1 for x, y in zip(m, j) if x == a and y == b)
                 for a in ("GOOD", "BAD") for b in ("GOOD", "BAD")}
    per_ext = {}
    for ext in sorted({i["extractor"] for i in items}):
        sub = [i for i in items if i["extractor"] == ext]
        per_ext[ext] = {"n": len(sub), "agree": sum(i["metric"] == i["judge"] for i in sub),
                        "metric_good": sum(i["metric"] == "GOOD" for i in sub),
                        "judge_good": sum(i["judge"] == "GOOD" for i in sub)}
    return {"n": len(items), "agreement": sum(a == b for a, b in zip(m, j)) / len(m),
            "metric_good_rate": m.count("GOOD") / len(m), "judge_good_rate": j.count("GOOD") / len(j),
            "cohen_kappa": stats.cohen_kappa(m, j), "cohen_kappa_ci95": kappa_ci(m, j),
            "confusion": confusion, "per_extractor": per_ext}


def run(n: int = 60, mock: bool = False, seed: int = 7, results_dir: Path = RESULTS,
        per_extractor: int | None = None, out_name: str | None = None) -> dict:
    """Judge a seeded sample of test (extractor, page) outputs.

    n picks a plain random sample; per_extractor (if given) picks that many pages
    for every extractor instead."""
    results_dir = Path(results_dir)
    name, judge = pick_judge(mock)
    out_path = results_dir / (out_name or ("judge_mock.json" if mock else "judge.json"))
    if judge is None:
        res = {"skipped": True, "reason": "no GROQ_API_KEY or ANTHROPIC_API_KEY set; run with --mock for an offline pipeline check"}
        out_path.write_text(json.dumps(res, indent=2))
        return res
    model = None
    if name == "groq":
        model = os.environ.get("JUDGE_MODEL", GROQ_DEFAULT_MODEL)
    elif name == "anthropic":
        model = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5")
    gold = {g["doc_id"]: g for g in build_corpus.load_gold()}
    outputs = {}
    with open(results_dir / "outputs.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            outputs[(o["extractor"], o["doc_id"])] = o["text"]
    with open(results_dir / "per_doc.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test"]
    if per_extractor:
        sample = stratified_sample(rows, per_extractor, seed)
    else:
        sample = random.Random(seed).sample(rows, min(n, len(rows)))
    items, errors = [], []
    for r in sample:
        g = "\n".join(gold[r["doc_id"]]["main"])[:MAX_CHARS]
        o = outputs[(r["extractor"], r["doc_id"])][:MAX_CHARS]
        try:
            jl = judge(g, o)
        except Exception as e:  # noqa: BLE001 - one failed API call must not lose the whole run
            errors.append({"extractor": r["extractor"], "doc_id": r["doc_id"],
                           "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        items.append({"extractor": r["extractor"], "doc_id": r["doc_id"], "f1": round(float(r["f1"]), 4),
                      "leak_rate": round(float(r["leak_rate"]), 4), "metric": metric_label(r), "judge": jl})
    if not items:
        res = {"skipped": True, "reason": "every judge call failed", "judge": name, "errors": errors}
        out_path.write_text(json.dumps(res, indent=2))
        return res
    res = {"skipped": False, "judge": name, "model": model, "seed": seed,
           "sampling": f"{per_extractor} per extractor" if per_extractor else f"random {n}",
           "n_errors": len(errors), **summarize(items), "items": items, "errors": errors}
    out_path.write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--per-extractor", type=int, default=None,
                    help="judge this many test pages for every extractor instead of a random n")
    ap.add_argument("--out-name", default=None, help="file name inside results/ (default judge.json)")
    a = ap.parse_args()
    r = run(a.n, a.mock, per_extractor=a.per_extractor, out_name=a.out_name)
    print(json.dumps({k: v for k, v in r.items() if k != "items"}, indent=2))
