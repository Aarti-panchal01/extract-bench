"""Run every extractor on one page and show what each one kept.

    python -m extract_bench.demo                     # default page: blog_comments-2
    python -m extract_bench.demo cookie_modal-3      # any doc_id from corpus/gold.jsonl
    python -m extract_bench.demo --html page.html    # your own file (no gold, so no scores)
    python -m extract_bench.demo --lines 4           # how many output lines to print per tool

For a corpus page it prints a score table (F1, leak rate, failure labels) and
the first lines of each tool's output, with leaked boilerplate listed by kind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import adapters, build_corpus, metrics, taxonomy

DEFAULT_DOC = "blog_comments-2"


def _first_lines(text: str, n: int, width: int = 96) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = [(ln if len(ln) <= width else ln[: width - 3] + "...") for ln in lines[:n]]
    if len(lines) > n:
        out.append(f"... ({len(lines) - n} more lines)")
    return out or ["(empty output)"]


def run_all(html: str) -> dict[str, dict]:
    outs = {}
    for name, fn in adapters.available().items():
        try:
            outs[name] = {**fn(html), "error": None}
        except Exception as e:  # noqa: BLE001 - show a crash, do not stop the demo
            outs[name] = {"title": None, "text": "", "error": f"{type(e).__name__}: {e}"}
    return outs


def render(doc_id: str | None, html: str, lines: int) -> str:
    gold = None
    if doc_id:
        gold = next(g for g in build_corpus.load_gold() if g["doc_id"] == doc_id)
    outs = run_all(html)
    buf: list[str] = []
    if gold:
        buf.append(f"page: {doc_id}  type: {gold['page_type']}  lang: {gold['lang']}  split: {gold['split']}")
        buf.append(f"gold title: {gold['title']}")
        buf.append(f"gold main text: {len(metrics.tokens(chr(10).join(gold['main'])))} tokens, "
                   f"{len(gold['boilerplate'])} boilerplate snippets planted")
        buf.append("")
        buf.append(f"{'extractor':<18} {'F1':>5} {'P':>5} {'R':>5} {'leak':>5}  labels")
        scored = {}
        for name, o in outs.items():
            s = metrics.score(o, gold)
            s["error"] = o["error"]
            s["page_type"] = gold["page_type"]
            scored[name] = s
            labs = ", ".join(taxonomy.label(s)) or "-"
            buf.append(f"{name:<18} {s['f1']:>5.2f} {s['precision']:>5.2f} {s['recall']:>5.2f} "
                       f"{s['leak_rate']:>5.2f}  {labs}")
    else:
        buf.append("no gold for this file, so no scores; showing raw output only")
    for name, o in outs.items():
        buf.append("")
        n_words = len((o["text"] or "").split())
        buf.append(f"--- {name}  ({n_words} words, title: {o['title']!r})")
        if o["error"]:
            buf.append(f"    crash: {o['error']}")
        for ln in _first_lines(o["text"], lines):
            buf.append(f"    {ln}")
        if gold:
            kinds: dict[str, int] = {}
            for x in scored[name]["leaked_snippets"]:
                kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
            if kinds:
                buf.append("    leaked: " + ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))
    return "\n".join(buf)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc_id", nargs="?", default=None)
    ap.add_argument("--html", type=Path, default=None, help="score-free run on your own HTML file")
    ap.add_argument("--lines", type=int, default=3)
    a = ap.parse_args(argv)
    if a.html:
        html, doc_id = a.html.read_text(encoding="utf-8", errors="replace"), None
    else:
        doc_id = a.doc_id or DEFAULT_DOC
        ids = {g["doc_id"] for g in build_corpus.load_gold()}
        if doc_id not in ids:
            print(f"unknown doc_id {doc_id!r}; pick one from corpus/gold.jsonl", file=sys.stderr)
            return 2
        html = build_corpus.load_html(doc_id)
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(doc_id, html, a.lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
