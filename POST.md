# My benchmark ranked extractors one way. Two sets of real pages ranked them two other ways.

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

## Then I checked it on many sites

Wikipedia is one site, so I added a second set of real pages. It is the public article-extraction benchmark from Zyte (MIT licence): 181 news and blog pages from 126 sites, with body text labelled by their team. I used all of it, and I did not retune anything.

- readability-lxml: 0.960 [0.948, 0.970]
- trafilatura, tuned on my synthetic dev pages: 0.960 [0.946, 0.971]
- trafilatura, default: 0.949 [0.931, 0.964]
- jusText: 0.718 [0.666, 0.769]

The top two are tied, also when I resample whole sites. jusText is fourth, with an empty output on 30 of 181 pages. So the Wikipedia flip was a Wikipedia result. On many sites the synthetic top two hold up, and jusText sits in the middle, not first and not last.

## What it means if you benchmark extractors

1. A tool that is last on one page mix can be first on another. Test on your own mix.
2. Treat empty output as a failure, not a result.
3. A benchmark you wrote yourself can only rank the pages you thought of.

I also checked my pass/fail rule against two LLM judges on 140 outputs. Kappa was 0.74 [0.61, 0.86] with qwen/qwen3.8-27b and 0.52 [0.36, 0.67] with openai/gpt-oss-120b. The two judges agreed with each other at 0.53 [0.37, 0.69].

## What this does not show

- It is not one final ranking. Wikipedia is 40 articles on one template. The Zyte set is news and blog pages only, and its authors published results for these tools on it, so the tools may have been tuned against it.
- It says nothing about non-English pages, recipes, forums or listings. Neither real set has them.
- No human labels exist for the judges, and the Wikipedia gold leaves out infobox text and tables.

One command reruns everything. The two real-page slices ship ids, links and hashes, not the text (CC BY-SA for Wikipedia, and the Zyte pages belong to the sites that published them).
