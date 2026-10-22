# We ran 6 open-source extractors on 40 tricky pages. Here is where each one breaks.

Every agent that reads the web starts the same way. It fetches HTML and turns it into text a model can read. If that step keeps the cookie banner and drops the recipe, nothing after it can fix the answer.

So I built a small benchmark for that first step: 60 synthetic pages across 10 types. News, blogs with comments, docs with code, spec tables, forums, recipes, listing pages that should give back almost nothing, pages under a cookie banner and modal, div-only layouts, and six non-English languages. Gold text is known by construction. I tuned on 20 pages and report only the other 40.

The six tools: trafilatura, readability-lxml, jusText, html2text, markdownify, and a naive BeautifulSoup `get_text()` as the floor. All ran on defaults, plus one trafilatura row tuned on dev pages.

## The headline

readability-lxml scored highest: mean token F1 0.93 (95% CI 0.90 to 0.95). Tuned trafilatura came second at 0.84 (0.75 to 0.91). A paired bootstrap over the 40 pages puts the gap of 0.085 at CI 0.018 to 0.166, which looks real.

It is not that solid. Pages of one type share a template, so they are not 40 independent pages. Resampling whole page types widens the interval to minus 0.005 to 0.227, which crosses zero.

Most of the gap comes from one page type. On listing pages, trafilatura kept every product card while readability kept little more than the intro line. My gold says only the intro counts, and that is a judgment call. With the 4 listing pages dropped, the gap shrinks to 0.020 (CI minus 0.018 to 0.072). The two are **not significantly different**.

So the honest headline: the top two are statistically tied, and the ranking hangs on one definition of what a listing page contains.

## Three failures worth seeing

**1. Cookie text treated as the article.** On one page built only from divs, with the consent box first in the body, both top tools opened their output with:

> We use cookies and similar technologies to personalise content, measure advertising and improve your experience on our site. By clicking Accept all you consent to the storage of cookies...

trafilatura scored F1 0.74 on that page and readability 0.71. Recall was perfect; the junk simply came along.

**2. A listing page read as content.** On a "Winter jackets" listing, trafilatura returned all 20 product cards, one per line:

> Velo Ultralight winter jacketUSD 132.50

Precision was 0.12. An agent now has 20 extra "facts". (The missing space is in my markup, not trafilatura's fault.)

**3. Silent empty output.** jusText returned an empty string, with no error, on 15 of 40 test pages. That is every non-English page (its default stoplist is English), every recipe and listing, and three of four forum threads. A pipeline reads that as "no text here", worse than noise.

Other patterns from the failure taxonomy:

- trafilatura keeps reader comments by default (`include_comments=True`). Turning that off was the only change the dev tuning picked, and it removed comment leaks on 4 of 40 test pages.
- readability-lxml's default `title()` returns the HTML `<title>` with the site name attached, so 0 of 40 matched the headline. Its `short_title()` helper matched 35. trafilatura matched all 40.
- html2text and markdownify are converters, not extractors. They kept everything, leaked nav menus on all 40 pages, and returned about 1.7 times the real word count.
- Code and tables survived intact everywhere except jusText.

## What this means if you build agents

1. Test on your own page mix. Averages hide the page type where a tool falls apart.
2. Read the defaults. One flag changed whether user comments counted as the article.
3. Treat empty output as a failure, not a result. Log it and fall back to a second extractor.
4. A markdown converter is not an extractor. It hands the model every menu and footer.
5. Watch consent boxes and div-only layouts. They fooled both of the best tools here.

## Limits of this benchmark

- **Synthetic pages.** Template text, and layouts that are my guesses at common patterns. Real pages are messier, and studies on real crawls may rank these tools differently.
- **Same author for pages and gold.** I decided what counts as content. The listing result shows how far one such decision moves a ranking.
- **No JavaScript rendering.** Static HTML only. Pages built in the browser are out of scope.
- **Small n, wide intervals.** 40 test pages, 4 per type, built from 10 templates. The per-type heatmap shows direction, not a ranking.
- **Metric is not a human.** Bag-of-words F1 ignores order and formatting. I checked it against two LLM judges on 140 outputs. Kappa was 0.74 with one and 0.52 with the other, and the two judges agreed with each other at only 0.53. Where both judges disagreed with the metric (9 cases), the metric was the lenient one every time. No human labels yet.
- **Tuning was uneven.** Only trafilatura got a tuned row. In a side check outside the ranking, jusText with the matching stoplist recovered the German and French pages (F1 1.00 and 0.89), but still returned nothing on Italian and Hindi.
- **Latency is one laptop.** Medians were 1 to 12 ms per page. Use them for order only.

One command rebuilds the corpus from a seed, reruns every tool, and regenerates every number and chart here (latency varies a little run to run). Library versions are pinned and printed in the results header.
