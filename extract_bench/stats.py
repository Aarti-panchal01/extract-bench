"""Seeded bootstrap statistics.

- bootstrap_ci: percentile CI of the mean, resampling documents with replacement
- paired_bootstrap: CI of mean(A - B) using the SAME resampled documents for
  both systems, which is the right test when both ran on the same pages
- cohen_kappa: agreement between two binary/categorical labelings
"""

from __future__ import annotations

from collections import Counter

import numpy as np

DEFAULT_SEED = 1234
DEFAULT_ITERS = 10_000


def bootstrap_ci(values, iters: int = DEFAULT_ITERS, alpha: float = 0.05, seed: int = DEFAULT_SEED) -> dict:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(iters, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {"mean": float(x.mean()), "lo": float(lo), "hi": float(hi), "n": int(x.size)}


def paired_bootstrap(a, b, iters: int = DEFAULT_ITERS, alpha: float = 0.05, seed: int = DEFAULT_SEED) -> dict:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired bootstrap needs equal-length arrays (same documents)")
    d = a - b
    ci = bootstrap_ci(d, iters=iters, alpha=alpha, seed=seed)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(iters, d.size))
    means = d[idx].mean(axis=1)
    # two-sided bootstrap p-value: how often the resampled mean falls on the other side of 0
    p = 2 * min((means <= 0).mean(), (means >= 0).mean())
    significant = not (ci["lo"] <= 0 <= ci["hi"])
    return {
        "mean_diff": ci["mean"],
        "lo": ci["lo"],
        "hi": ci["hi"],
        "n": ci["n"],
        "p_value": float(min(1.0, p)),
        "significant": significant,
        "verdict": "significantly different" if significant else "not significantly different",
    }


def cohen_kappa(labels_a, labels_b) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(labels_a)
    po = sum(x == y for x, y in zip(labels_a, labels_b)) / n
    ca, cb = Counter(labels_a), Counter(labels_b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)
