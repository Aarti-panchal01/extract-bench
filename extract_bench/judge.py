"""Optional LLM judge, used only to measure how well the token metric agrees
with a model's opinion. It is never part of the main ranking.

    python -m extract_bench.judge                 # skipped unless a key is set
    python -m extract_bench.judge --mock          # offline stand-in judge (pipeline check only)
    GROQ_API_KEY=... python -m extract_bench.judge --n 60
    ANTHROPIC_API_KEY=... python -m extract_bench.judge --n 60

The metric label for a page is GOOD when F1 >= 0.8 and leak rate <= 0.2.
The judge sees the gold content and the extractor output and answers GOOD or
BAD. Agreement is reported as Cohen's kappa. Results go to results/judge.json.
Model names can be changed with JUDGE_MODEL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import urllib.request
from pathlib import Path

from . import build_corpus, stats

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

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


def mock_judge(gold: str, output: str) -> str:
    """Offline stand-in: a crude length-ratio rule. Exists so the pipeline can be
    tested without a key. Its kappa says nothing about real LLM judges."""
    g, o = len(gold.split()), len(output.split())
    return "GOOD" if g and 0.8 <= o / g <= 1.3 else "BAD"


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https endpoints
        return json.loads(r.read())


def groq_judge(gold: str, output: str) -> str:
    body = {"model": os.environ.get("JUDGE_MODEL", "llama-3.3-70b-versatile"), "temperature": 0,
            "max_tokens": 3, "messages": [{"role": "user", "content": PROMPT.format(gold=gold, output=output)}]}
    data = _post("https://api.groq.com/openai/v1/chat/completions",
                 {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json"}, body)
    return "GOOD" if "GOOD" in data["choices"][0]["message"]["content"].upper() else "BAD"


def anthropic_judge(gold: str, output: str) -> str:
    body = {"model": os.environ.get("JUDGE_MODEL", "claude-haiku-4-5"), "max_tokens": 5,
            "messages": [{"role": "user", "content": PROMPT.format(gold=gold, output=output)}]}
    data = _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                  "content-type": "application/json"}, body)
    text = "".join(b.get("text", "") for b in data.get("content", []))
    return "GOOD" if "GOOD" in text.upper() else "BAD"


def pick_judge(mock: bool):
    if mock:
        return "mock", mock_judge
    if os.environ.get("GROQ_API_KEY"):
        return "groq", groq_judge
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", anthropic_judge
    return None, None


def run(n: int = 60, mock: bool = False, seed: int = 7, results_dir: Path = RESULTS) -> dict:
    results_dir = Path(results_dir)
    name, judge = pick_judge(mock)
    out_path = results_dir / ("judge_mock.json" if mock else "judge.json")
    if judge is None:
        res = {"skipped": True, "reason": "no GROQ_API_KEY or ANTHROPIC_API_KEY set; run with --mock for an offline pipeline check"}
        out_path.write_text(json.dumps(res, indent=2))
        return res
    gold = {g["doc_id"]: g for g in build_corpus.load_gold()}
    outputs = {}
    with open(results_dir / "outputs.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            outputs[(o["extractor"], o["doc_id"])] = o["text"]
    with open(results_dir / "per_doc.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] == "test"]
    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))
    m_labels, j_labels, items = [], [], []
    for r in sample:
        g = "\n".join(gold[r["doc_id"]]["main"])[:4000]
        o = outputs[(r["extractor"], r["doc_id"])][:4000]
        jl = judge(g, o)
        ml = metric_label(r)
        m_labels.append(ml)
        j_labels.append(jl)
        items.append({"extractor": r["extractor"], "doc_id": r["doc_id"], "metric": ml, "judge": jl})
    agree = sum(a == b for a, b in zip(m_labels, j_labels)) / len(m_labels)
    res = {"skipped": False, "judge": name, "n": len(items), "agreement": agree,
           "cohen_kappa": stats.cohen_kappa(m_labels, j_labels), "items": items}
    out_path.write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    r = run(a.n, a.mock)
    print(json.dumps({k: v for k, v in r.items() if k != "items"}, indent=2))
