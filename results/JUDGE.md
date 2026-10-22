# LLM judge vs the metric rule

Metric rule: GOOD when F1 >= 0.8 and leak rate <= 0.2, else BAD. Each judge sees the gold main text and the extractor output and answers GOOD or BAD. Test split only. Kappa CIs are a percentile bootstrap over items (2,000 resamples, seed 7).

| Judge | n | errors | Agreement | Kappa [95% CI] | Metric GOOD | Judge GOOD |
|---|---|---|---|---|---|---|
| openai/gpt-oss-120b | 140 | 0 | 0.82 | 0.52 [0.36, 0.67] | 0.32 | 0.14 |
| qwen/qwen3.8-27b | 140 | 0 | 0.89 | 0.74 [0.61, 0.86] | 0.32 | 0.27 |

## openai/gpt-oss-120b (judge_gpt-oss-120b.json, 20 per extractor, seed 7)

| | judge GOOD | judge BAD |
|---|---|---|
| metric GOOD | 20 | 25 |
| metric BAD | 0 | 95 |

| Extractor | n | agree | metric GOOD | judge GOOD |
|---|---|---|---|---|
| bs4-naive | 20 | 20 | 0 | 0 |
| html2text | 20 | 20 | 0 | 0 |
| justext | 20 | 15 | 6 | 1 |
| markdownify | 20 | 20 | 0 | 0 |
| readability-lxml | 20 | 12 | 14 | 6 |
| trafilatura | 20 | 14 | 11 | 5 |
| trafilatura (best-config) | 20 | 14 | 14 | 8 |

## qwen/qwen3.8-27b (judge_qwen3.8-27b.json, 20 per extractor, seed 7)

| | judge GOOD | judge BAD |
|---|---|---|
| metric GOOD | 34 | 11 |
| metric BAD | 4 | 91 |

| Extractor | n | agree | metric GOOD | judge GOOD |
|---|---|---|---|---|
| bs4-naive | 20 | 20 | 0 | 0 |
| html2text | 20 | 20 | 0 | 0 |
| justext | 20 | 16 | 6 | 2 |
| markdownify | 20 | 20 | 0 | 0 |
| readability-lxml | 20 | 15 | 14 | 15 |
| trafilatura | 20 | 18 | 11 | 11 |
| trafilatura (best-config) | 20 | 16 | 14 | 10 |

## Judge vs judge

| Pair | n | Agreement | Kappa [95% CI] |
|---|---|---|---|
| openai/gpt-oss-120b vs qwen/qwen3.8-27b | 140 | 0.84 | 0.53 [0.37, 0.69] |

Items judged by all: 140. All judges gave the same label on 118; the metric rule matches them on 109.

Items where the judges agree with each other but not with the metric rule:

| Extractor | Page | F1 | Leak | Metric | Judges |
|---|---|---|---|---|---|
| justext | docs_code-2 | 0.90 | 0.14 | GOOD | BAD |
| justext | news-1 | 0.93 | 0.00 | GOOD | BAD |
| justext | product_spec-5 | 0.85 | 0.11 | GOOD | BAD |
| readability-lxml | forum-3 | 0.89 | 0.12 | GOOD | BAD |
| readability-lxml | product_spec-1 | 0.91 | 0.20 | GOOD | BAD |
| trafilatura | forum-4 | 0.87 | 0.00 | GOOD | BAD |
| trafilatura (best-config) | forum-2 | 0.85 | 0.00 | GOOD | BAD |
| trafilatura (best-config) | news-5 | 0.92 | 0.20 | GOOD | BAD |
| trafilatura (best-config) | product_spec-1 | 0.83 | 0.10 | GOOD | BAD |
