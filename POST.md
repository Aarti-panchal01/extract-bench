# My benchmark ranked extractors one way. 40 real pages ranked them the other way.

Every agent that reads the web first turns HTML into text. I built a small benchmark of open-source extractors for that step.

On my 40 synthetic test pages, readability-lxml came first: F1 0.925 [0.898, 0.949]. jusText came last: 0.554 [0.418, 0.687]. I wrote those pages and their gold text.

Then I added 40 real English Wikipedia articles. A random draw picked them, by a rule I wrote down before any tool ran. The gold is the Wikipedia API's plain-text extract, so I did not write it. Same code, same metric.

The order flipped.

- jusText: 0.849 [0.812, 0.882]
- readability-lxml: 0.788 [0.744, 0.829]
- trafilatura: 0.735 [0.694, 0.775]

Spearman rank correlation with the synthetic order is 0.20 over 7 rows. What held: html2text, markdownify and the naive BeautifulSoup baseline stayed at the bottom (F1 0.588 to 0.626).

## Why it flipped

On the synthetic set, jusText returned an empty string on 15 of 40 pages. Those were non-English pages, recipes, listings and forum threads. Wikipedia is all English articles. There jusText was the most precise tool (precision 0.936) and trafilatura was the least precise of the top three (0.598, with recall 1.000).

So the synthetic set punished jusText for page types the real set does not contain. Even on the synthetic set, the top two were not significantly different once I resampled whole page types: [-0.005, +0.227].

## What it means if you benchmark extractors

1. A tool that is last on one page mix can be first on another. Test on your own mix.
2. Treat empty output as a failure, not a result.
3. A benchmark you wrote yourself can only rank the pages you thought of.

I also checked my pass/fail rule against two LLM judges on 140 outputs. Kappa was 0.74 [0.61, 0.86] with qwen/qwen3.8-27b and 0.52 [0.36, 0.67] with openai/gpt-oss-120b. The two judges agreed with each other at 0.53 [0.37, 0.69].

## What this does not show

- It is not a new ranking. It is 40 articles on one site template, not 40 layouts.
- It says nothing about non-English pages, recipes, forums or listings. The Wikipedia slice has none.
- No human labels exist for the judges, and the Wikipedia gold leaves out infobox text and tables.

One command reruns everything. The Wikipedia slice ships page ids, revision links and hashes, not the text (CC BY-SA).
