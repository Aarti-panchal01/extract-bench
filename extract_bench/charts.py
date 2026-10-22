"""Static PNG charts (matplotlib, Agg backend, no display needed).

Style: one blue for single-series charts, a one-hue blue ramp for the heatmap,
direct labels instead of a legend, recessive grid, no dual axes.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from . import build_corpus  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
BLUE_DARK = "#104281"
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _style(ax, title: str, subtitle: str | None = None):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.title.set_color(INK)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=18 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")


def f1_ci(summary: list[dict], path: Path):
    rows = list(reversed(summary))  # best at top
    names = [r["extractor"] for r in rows]
    means = [r["f1"]["mean"] for r in rows]
    lo = [r["f1"]["mean"] - r["f1"]["lo"] for r in rows]
    hi = [r["f1"]["hi"] - r["f1"]["mean"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    y = range(len(rows))
    ax.barh(y, means, height=0.55, color=BLUE, edgecolor=SURFACE, linewidth=2)
    ax.errorbar(means, y, xerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=1.2, capsize=3)
    for i, r in enumerate(rows):
        ax.text(r["f1"]["hi"] + 0.012, i, f"{r['f1']['mean']:.2f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(list(y), names)
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("Token F1 vs gold main text (test pages)", color=INK_2, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    n = summary[0]["f1"]["n"]
    _style(ax, "Content F1 by extractor", f"Mean with 95% bootstrap CI, n = {n} pages")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def heatmap(by_type: dict, path: Path):
    names = list(by_type)
    types = build_corpus.PAGE_TYPES
    data = [[by_type[n][t] for t in types] for n in names]
    cmap = LinearSegmentedColormap.from_list("blue", RAMP)
    fig, ax = plt.subplots(figsize=(10, 4.4), dpi=150)
    im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(types)), [t.replace("_", "\n") for t in types], fontsize=8)
    ax.set_yticks(range(len(names)), names, fontsize=9)
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color=SURFACE if v >= 0.55 else INK)
    ax.set_xticks([x - 0.5 for x in range(1, len(types))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(names))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.ax.tick_params(labelsize=8, colors=INK_2)
    cb.outline.set_visible(False)
    _style(ax, "F1 by page type", "Each cell is the mean of 4 test pages, so read it as a direction, not a ranking")
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def leak_vs_recall(summary: list[dict], path: Path):
    fig, ax = plt.subplots(figsize=(7.5, 5), dpi=150)
    placed: list[tuple[float, float]] = []
    for r in sorted(summary, key=lambda r: -r["leak_rate"]["mean"]):
        x, y = r["recall"]["mean"], r["leak_rate"]["mean"]
        ax.scatter([x], [y], s=70, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        # simple label de-collision: push a label down until it clears earlier ones
        ly = y + 0.015
        while any(abs(ly - py) < 0.04 and abs(x - px) < 0.3 for px, py in placed):
            ly -= 0.045
        placed.append((x, ly))
        ax.annotate(r["extractor"], (x, y), xytext=(x + 0.015, ly), textcoords="data", fontsize=8.5, color=INK,
                    arrowprops=None if abs(ly - y) < 0.03 else {"arrowstyle": "-", "color": GRID, "lw": 0.8})
    ax.set_xlabel("Recall of gold content (higher is better)", color=INK_2, fontsize=9)
    ax.set_ylabel("Boilerplate leak rate (lower is better)", color=INK_2, fontsize=9)
    ax.set_xlim(0, 1.25)
    ax.set_ylim(-0.03, 1.0)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.text(1.22, -0.02, "ideal: bottom right", ha="right", va="bottom", fontsize=8, color=INK_2)
    _style(ax, "Keeping content vs keeping junk out", "Mean over test pages; each dot is one extractor config")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def latency(summary: list[dict], path: Path):
    rows = sorted(summary, key=lambda r: r["latency_ms_median"], reverse=True)
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    y = range(len(rows))
    vals = [r["latency_ms_median"] for r in rows]
    ax.barh(y, vals, height=0.55, color=BLUE, edgecolor=SURFACE, linewidth=2)
    for i, r in enumerate(rows):
        ax.text(vals[i] * 1.08, i, f"{vals[i]:.1f} ms (p90 {r['latency_ms_p90']:.1f})", va="center",
                fontsize=8.5, color=INK)
    ax.set_xscale("log")
    ax.set_yticks(list(y), [r["extractor"] for r in rows])
    ax.set_xlim(min(vals) / 1.6, max(vals) * 8)
    ax.set_xlabel("Median milliseconds per page, log scale (single core, this laptop)", color=INK_2, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    _style(ax, "Extraction latency", "Median of 3 timed runs per page; machine dependent")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def make_all(summary: list[dict], by_type: dict, test_rows: dict, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "f1_ci.png", out_dir / "f1_by_page_type.png", out_dir / "leak_vs_recall.png",
             out_dir / "latency.png"]
    f1_ci(summary, paths[0])
    heatmap(by_type, paths[1])
    leak_vs_recall(summary, paths[2])
    latency(summary, paths[3])
    return paths
