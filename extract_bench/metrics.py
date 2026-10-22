"""Per-document metrics.

All text metrics work on normalized tokens:
- markdown links/images are reduced to their visible text and bare URLs are
  dropped, so markdown output and plain-text output are scored the same way
- tokens are runs of letters/digits (Latin, accented Latin, Devanagari incl.
  vowel signs), lowercased; underscores and punctuation split tokens

Metric definitions (one document):
- precision / recall / f1: bag-of-tokens overlap with the gold main text
  (multiset intersection). The gold title is removed once from the start
  region of the output first, so including or omitting the title in the body
  text is neither rewarded nor punished (title is scored separately).
- leak_rate: share of scorable boilerplate snippets that leaked. A snippet
  leaked when at least half of its n-grams (n=4, or its length if shorter) that
  do NOT also occur in the gold main text are present in the output.
- table_row_recall: share of gold table rows whose tokens appear as a
  contiguous run in the output tokens.
- code_line_recall: same, for code lines.
- code_line_exact: share of code lines that appear verbatim (after strip) as
  a line of the output; catches flattened or escaped code.
- title_match: 1 if the normalized predicted title equals the gold title.
"""

from __future__ import annotations

import re
from collections import Counter

TOKEN_RE = re.compile(r"(?:[^\W_]|[ऀ-ॣ०-ॿ])+", re.UNICODE)
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"https?://\S+|(?<![\w])/[\w\-./?=#&]+")
LEAK_N = 4
LEAK_THRESHOLD = 0.5


def normalize(text: str) -> str:
    if not text:
        return ""
    text = MD_IMAGE.sub(r"\1", text)
    text = MD_LINK.sub(r"\1", text)
    text = URL.sub(" ", text)
    return text


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(normalize(text))]


def ngrams(toks: list[str], n: int) -> set[tuple[str, ...]]:
    if n <= 0 or len(toks) < n:
        return set()
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def contains_run(haystack: list[str], needle: list[str]) -> bool:
    """True if needle appears as a contiguous run inside haystack."""
    if not needle:
        return False
    n = len(needle)
    first = needle[0]
    for i in range(len(haystack) - n + 1):
        if haystack[i] == first and haystack[i:i + n] == needle:
            return True
    return False


def remove_title(pred_toks: list[str], title_toks: list[str], window: int = 60) -> list[str]:
    """Remove the first occurrence of the title run if it starts in the first `window` tokens."""
    n = len(title_toks)
    if n == 0:
        return pred_toks
    for i in range(min(window, len(pred_toks) - n + 1)):
        if pred_toks[i:i + n] == title_toks:
            return pred_toks[:i] + pred_toks[i + n:]
    return pred_toks


def prf(pred: list[str], gold: list[str]) -> tuple[float, float, float]:
    if not pred or not gold:
        return 0.0, 0.0, 0.0
    overlap = sum((Counter(pred) & Counter(gold)).values())
    if overlap == 0:
        return 0.0, 0.0, 0.0
    p = overlap / len(pred)
    r = overlap / len(gold)
    return p, r, 2 * p * r / (p + r)


def leak_details(pred_toks: list[str], boilerplate: list[dict], gold_toks: list[str]) -> list[dict]:
    """For each boilerplate snippet: scorable?, leaked?, matched fraction."""
    pred_cache: dict[int, set] = {}
    gold_cache: dict[int, set] = {}
    out = []
    for snip in boilerplate:
        st = tokens(snip["text"])
        n = min(LEAK_N, len(st))
        if n == 0:
            out.append({"kind": snip["kind"], "scorable": False, "leaked": False, "frac": 0.0})
            continue
        if n not in gold_cache:
            gold_cache[n] = ngrams(gold_toks, n)
            pred_cache[n] = ngrams(pred_toks, n)
        own = ngrams(st, n) - gold_cache[n]
        if not own:
            out.append({"kind": snip["kind"], "scorable": False, "leaked": False, "frac": 0.0})
            continue
        frac = len(own & pred_cache[n]) / len(own)
        out.append({"kind": snip["kind"], "scorable": True, "leaked": frac >= LEAK_THRESHOLD, "frac": frac,
                    "text": snip["text"]})
    return out


def run_recall(pred_toks: list[str], units: list[str]) -> float | None:
    units_t = [tokens(u) for u in units]
    units_t = [u for u in units_t if u]
    if not units_t:
        return None
    return sum(contains_run(pred_toks, u) for u in units_t) / len(units_t)


def _line_variants(line: str) -> set[str]:
    """Ways a code line may legitimately appear in markdown or text output."""
    ln = line.rstrip()
    out = {ln}
    # markdown indented code blocks shift every line by 4 spaces (or a tab)
    for prefix in ("    ", "\t", "        "):
        if ln.startswith(prefix):
            out.add(ln[len(prefix):])
    # fences / inline backticks are formatting, not content
    out |= {v.strip("`") for v in list(out)}
    return out


def code_exact(pred_text: str, code_lines: list[str]) -> float | None:
    """Share of code lines found verbatim, INCLUDING leading indentation."""
    lines = [c.rstrip() for c in code_lines if c.strip()]
    if not lines:
        return None
    have: set[str] = set()
    for ln in (pred_text or "").splitlines():
        have |= _line_variants(ln)
    return sum(ln in have for ln in lines) / len(lines)


def norm_title(t: str | None) -> list[str]:
    return tokens(t or "")


def score(pred: dict, gold: dict) -> dict:
    """Score one extractor output against one gold record."""
    text = pred.get("text") or ""
    gold_toks = tokens("\n".join(gold["main"]))
    title_toks = norm_title(gold["title"])
    pred_toks = remove_title(tokens(text), title_toks)
    p, r, f = prf(pred_toks, gold_toks)
    leaks = leak_details(pred_toks, gold["boilerplate"], gold_toks)
    scorable = [x for x in leaks if x["scorable"]]
    leaked = [x for x in scorable if x["leaked"]]
    pt = norm_title(pred.get("title"))
    return {
        "precision": p,
        "recall": r,
        "f1": f,
        "n_pred_tokens": len(pred_toks),
        "n_gold_tokens": len(gold_toks),
        "leak_rate": (len(leaked) / len(scorable)) if scorable else 0.0,
        "n_leaked": len(leaked),
        "n_boilerplate": len(scorable),
        "leaked_kinds": sorted({x["kind"] for x in leaked}),
        "leaked_snippets": [{"kind": x["kind"], "text": x["text"]} for x in leaked],
        "table_row_recall": run_recall(pred_toks, gold.get("table_rows", [])),
        "code_line_recall": run_recall(pred_toks, gold.get("code_lines", [])),
        "code_line_exact": code_exact(text, gold.get("code_lines", [])),
        "title_match": float(bool(pt) and pt == title_toks),
        "title_present": float(bool(pt)),
    }
