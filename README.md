# extract-bench

A small, reproducible benchmark of open-source HTML-to-text extractors. It runs six tools on 60 seeded synthetic pages, scores them against gold text that is known by construction, puts 95% bootstrap confidence intervals on every headline number, and labels each failure with a rule-based taxonomy.

Everything runs locally. No API keys, no network at run time, no paid services.

![F1 with confidence intervals](charts/f1_ci.png)

## Why this exists

Every AI agent that reads the web does the same first step: fetch HTML, turn it into text. If that step keeps the cookie banner and drops the recipe, nothing after it can fix the answer. Teams that pick a web tool for their agent usually look at a vendor's own numbers or a single average.

This project is an outside-in benchmark of other people's tools, done the way I think benchmark work should be done:

- a corpus with known gold, a dev/test split, and results reported on test only
- confidence intervals, and a paired test that says "not significantly different" when the interval crosses zero
- a failure taxonomy that shows *how* each tool breaks, not just a score
- a written "limits of this benchmark" section, because a benchmark that hides its limits is marketing

The write-up for a general audience is in [POST.md](POST.md).

## Headline results (40 test pages)

| Extractor | F1 [95% CI] | Leak rate | Median ms |
|---|---|---|---|
| readability-lxml | 0.925 [0.898, 0.949] | 0.181 | 4 |
| trafilatura (best-config) | 0.840 [0.753, 0.914] | 0.111 | 12 |
| trafilatura | 0.831 [0.746, 0.905] | 0.160 | 11 |
| html2text | 0.706 [0.634, 0.769] | 0.811 | 1 |
| bs4-naive | 0.693 [0.621, 0.756] | 0.885 | 1 |
| markdownify | 0.693 [0.622, 0.755] | 0.811 | 4 |
| justext | 0.554 [0.418, 0.687] | 0.124 | 4 |

- Top two, paired bootstrap over pages: readability-lxml minus tuned trafilatura = +0.085 [+0.018, +0.166], significantly different.
- But pages of one type share a template, so they are not independent. Resampling whole page types gives [-0.005, +0.227]: **not significantly different**.
- Sensitivity check without the 4 listing pages (where the gold is a judgment call): +0.020 [-0.018, +0.072], **not significantly different** either way of resampling. Most of the gap comes from one page type.
- jusText returned an empty string with no error on 15 of 40 test pages (all non-English pages, all recipes, all listings, 3 forum threads).
- html2text and markdownify keep everything: recall 1.00, but nav menus leak on 40 of 40 pages and output is about 1.7 times the real content.
- trafilatura keeps reader comments by default. Dev tuning picked `include_comments=False`, which removed comment leaks on 4 test pages.

Full generated tables: [results/RESULTS.md](results/RESULTS.md). Latency numbers come from one Windows laptop and are only good for ordering.

![F1 by page type](charts/f1_by_page_type.png)

![Leak vs recall](charts/leak_vs_recall.png)

## How to run

Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m extract_bench.build_corpus     # rebuild the 60 fixtures + gold (deterministic)
python -m extract_bench.run              # full run: results/ and charts/ (about 30 seconds)
python -m extract_bench.run --quick      # fewer resamples, 1 timing repeat
python -m extract_bench.side_checks      # jusText stoplists + readability short_title() (not ranked)
python -m pytest -q                      # 70 tests (one runs the whole benchmark in --quick mode)
```

Optional LLM judge (off by default, never part of the ranking):

```bash
python -m extract_bench.judge            # writes results/judge.json with skipped: true if no key
python -m extract_bench.judge --mock     # offline stand-in, only checks the pipeline
GROQ_API_KEY=... python -m extract_bench.judge --n 60
```

The judge labels a sample of (extractor, page) outputs GOOD or BAD, and reports Cohen's kappa against the metric rule (F1 at least 0.8 and leak rate at most 0.2). It has not been run with a real model for the published results.

## The corpus

`extract_bench/build_corpus.py` generates 10 page types x 6 variants from a fixed seed:

| Page type | What makes it hard |
|---|---|
| news | related-articles block *inside* the article, share line, sidebar, noscript |
| blog_comments | reader comments right after the post (gold says comments are not content) |
| docs_code | `pre` code blocks with indentation, `<` and `**kwargs`, side nav, "on this page" TOC, options table |
| product_spec | spec table (some without `thead`), add-to-cart copy, "customers also bought" |
| forum | many short posts, signatures, reply buttons, forum rules box |
| recipe | short list items, ad slot, "jump to recipe" UI, reviews, nutrition table |
| listing | 12 to 24 product cards; gold is only the heading and intro line |
| cookie_modal | long consent text and a newsletter modal, sometimes first in the body, sometimes last |
| nested_div | no semantic tags, obfuscated class names, text split by `<br>`, one variant with no `h1` |
| non_english | Spanish, German, French, Portuguese, Italian, Hindi, with matching boilerplate |

Every page also has a script payload in `<head>`, a `<title>` that adds " | Site Name" to the visible headline, and half of them use div soup instead of `article`/`main`/`nav`.

Gold is recorded while the HTML is generated, so it is exact: main text units in reading order, boilerplate snippets tagged by kind, table rows, and code lines. The split is stratified: 2 dev and 4 test pages per type, 20 dev and 40 test in total. Tests check that every gold unit is really in its page, that no boilerplate snippet is inside the gold, that the split is disjoint, and that a rebuild gives byte-identical files.

## Metrics

All text is normalized first: markdown links and images become their visible text and URLs are dropped, so markdown output and plain text are scored the same way. Tokens are lowercased runs of letters and digits (Devanagari vowel signs stay attached).

- **Precision, recall, F1**: bag-of-tokens overlap with the gold main text. The gold title is removed once near the start of the output first, so putting the headline in the body text is neither rewarded nor punished.
- **Boilerplate leak rate**: share of boilerplate snippets that made it into the output. A snippet leaked when at least half of its 4-grams that are *not* also in the gold appear in the output.
- **Table rows kept**: share of rows whose tokens appear as one contiguous run.
- **Code lines kept / exact**: the same for code lines, plus an exact check that keeps leading indentation (a markdown 4-space shift is allowed).
- **Title match**: normalized predicted title equals the visible headline.
- **Latency**: median of 3 timed runs per page.

## Statistics

`extract_bench/stats.py`:

- Percentile bootstrap CI of the mean, resampling pages, 10,000 resamples, fixed seed. Same seed gives the same interval.
- Paired bootstrap on the per-page difference for two systems on the same pages. If the CI crosses 0 the verdict is "not significantly different".
- Cluster (page-type) paired bootstrap: the same test, but each resample draws whole page types. The 4 test pages of a type come from one template, so the page-level interval is too narrow when one type drives a gap. Both are reported for the top two; the per-row CIs in the tables are page-level.
- Cohen's kappa for the optional judge.

## Fairness rules

- Every tool runs on library defaults. The config used for each row is printed in the results table.
- readability-lxml returns cleaned HTML, not text. Its adapter turns that HTML into text with a small helper (`adapters/_text.py`) that only adds line breaks at block tags and ` | ` between table cells; it removes nothing except `script`/`style` and HTML comments.
- Titles use each library's default call. For readability that is `title()`, which returns the whole `<title>` tag (0 of 40 matches). Its `short_title()` helper strips the site name and matches 35 of 40 (side check, `results/side_checks.json`).
- Exactly one extra "best-config" row: trafilatura, tuned on the 20 dev pages over a 6-setting grid (`results/tuning.json`), then frozen.
- Only test-split numbers are reported.
- Library versions are pinned in `requirements.txt` and printed in the header of `results/summary.json` and `results/RESULTS.md`.
- An exception inside a library is recorded as a failure for that page (score 0, label `crash`), not a crashed run. No crashes happened in the published run.

## Failure taxonomy

`extract_bench/taxonomy.py` assigns fixed-threshold labels to each (tool, page): `crash`, `empty_output`, `low_recall`, `over_extraction`, six leak labels (nav or footer, consent or modal, related or teaser, comment or signature, script or noscript, commerce or listing), `table_lost`, `code_lost`, `code_flattened`, `title_wrong`. Counts per tool are in `results/taxonomy.json`; concrete examples with output excerpts are in `results/excerpts.json`.

## Limits

- **Synthetic pages.** Template text and my guesses at common layouts. Real pages are messier, and studies on real crawls may rank these tools differently.
- **Same author for pages and gold.** I decided what counts as content. The listing-page sensitivity check shows how much one decision can move the ranking.
- **No JavaScript rendering.** Static HTML only.
- **Small n, few templates.** 40 test pages, 4 per type, from 10 templates. Per-type cells are directions, not rankings, and the honest unit of variation is closer to 10 page types than 40 pages.
- **Metric is not a human.** Bag-of-words F1 ignores order and formatting. The judge that would measure this gap is built but not yet run with a real model.
- **Uneven tuning.** Only trafilatura got a tuned row. The side check shows jusText recovers on German and French with the right stoplist, but not on Italian or Hindi.
- **One machine** for latency. Latency also moves a little on every rerun; every other number is identical run to run.

## Layout

```
extract_bench/
  build_corpus.py   seeded generator, gold, split
  textbanks.py      sentence banks (main text and boilerplate kept apart)
  adapters/         one module per tool, common extract(html) -> {title, text}
  metrics.py        per-page scoring
  stats.py          bootstrap, paired bootstrap, kappa
  taxonomy.py       failure labels
  run.py            end-to-end run, writes results/
  charts.py         matplotlib charts
  judge.py          optional LLM judge
  side_checks.py    off-protocol checks, not ranked
corpus/             60 HTML fixtures + gold.jsonl
results/            summary.json, paired.json, taxonomy.json, excerpts.json, per_doc.csv, outputs.jsonl, RESULTS.md
charts/             f1_ci.png, f1_by_page_type.png, leak_vs_recall.png, latency.png
tests/              pytest suite
POST.md             plain-words write-up
```

Adding a tool means adding one adapter module and one line in `extract_bench/adapters/__init__.py`.
