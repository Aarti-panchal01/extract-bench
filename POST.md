# We ran 6 open-source extractors on 40 tricky pages. Here is where each one breaks.

Every agent that reads the web starts the same way. It fetches HTML and turns it into text a model can read. If that step keeps the cookie banner and drops the recipe, nothing after it can fix the answer.

So I built a small benchmark for that first step: 60 synthetic pages across 10 types. News, blogs with comments, docs with code, spec tables, forums, recipes, listing pages that should give back almost nothing, pages under a cookie banner and modal, div-only layouts, and six non-English languages. Each page comes with its gold text, known by construction. I tuned on 20 pages and report only the other 40.

The six tools: trafilatura, readability-lxml, jusText, html2text, markdownify, and a naive BeautifulSoup `get_text()` as the floor. All ran on defaults, plus one trafilatura row tuned on the dev pages only.

## The headline

readability-lxml scored highest: mean token F1 0.93 (95% CI 0.90 to 0.95). Tuned trafilatura came second at 0.84 (0.75 to 0.91). A paired bootstrap on the same 40 pages says the gap of 0.085 is real (CI 0.018 to 0.166).

But most of that gap comes from one page type. On listing pages, trafilatura kept every product card while readability kept little more than the intro line. My gold says only the intro counts, and that is a judgment call. With the 4 listing pages dropped, the gap shrinks to 0.020 (CI minus 0.018 to 0.072). The two are **not significantly different**.

So the honest headline: on the other 36 pages the top two are statistically tied, and the ranking hangs on one definition of what a listing page contains.

## Three failures worth seeing

**1. Cookie text treated as the article.** On one page built only from divs, with the consent box first in the body, both top tools opened their output with:

> We use cookies and similar technologies to personalise content, measure advertising and improve your experience on our site. By clicking Accept all you consent to the storage of cookies...

trafilatura scored F1 0.74 on that page and readability 0.71. Recall was perfect; the junk simply came along.

**2. A listing page read as content.** On a "Winter jackets" listing, trafilatura returned all 20 cards, and it glued names to prices:

> Velo Ultralight winter jacketUSD 132.50

Precision was 0.12. An agent now has 20 extra "facts" and broken tokens.

**3. Silent empty output.** jusText returned an empty string, with no error, on 15 of 40 test pages. That covers all four non-English test pages (its default stoplist is English), all four recipes, all four listings and three of the four forum threads. A pipeline reads that as "no text here", which is worse than noise.

Other patterns from the failure taxonomy:

- trafilatura keeps reader comments by default (`include_comments=True`). Turning that off was the only change the dev tuning picked, and it removed comment leaks on 4 of 40 test pages.
- readability-lxml returns the HTML `<title>` with the site name attached ("Story | Site"), so 0 of 40 titles matched the visible headline. trafilatura matched all 40.
- html2text and markdownify are converters, not extractors. They kept all the content, leaked nav menus on all 40 pages, and returned about 1.7 times as many words as the real content.
- Code and tables survived intact everywhere except jusText.

## What this means if you build agents

1. Test on your own page mix. Averages hide that each tool has one page type where it falls apart.
2. Read the defaults. One flag changed whether user comments counted as the article.
3. Treat empty output as a failure, not a result. Log it and fall back to a second extractor.
4. A markdown converter is not an extractor. It hands the model every menu and footer.
5. Watch consent boxes and div-only layouts. They fooled both of the best tools here.

## Limits of this benchmark

- **Synthetic pages.** The text comes from templates and the layouts are my guesses at common patterns. Real pages are messier, and studies on real crawls may rank these tools differently.
- **Same author for pages and gold.** I wrote the generator and decided what counts as content. The listing result shows how much one such decision can move a ranking.
- **No JavaScript rendering.** Every page is static HTML. Pages that build their content in the browser are out of scope.
- **Small n, wide intervals.** 40 test pages, 4 per type. The per-type heatmap shows direction, not a ranking. Some CIs are more than 0.25 wide.
- **Metric is not a human.** Bag-of-words F1 ignores order and formatting. An optional LLM judge (Cohen's kappa against the metric) is built but not yet run with a real model, so that gap is unmeasured.
- **Tuning was uneven.** Only trafilatura got a tuned row. In a side check outside the ranking, jusText with the matching stoplist recovered the German and French pages (F1 1.00 and 0.89), but still returned nothing on Italian and Hindi.
- **Latency is one laptop.** Medians were 1 to 12 ms per page. Use them for order, not as absolute numbers.

One command rebuilds the corpus from a seed, reruns every tool, and regenerates every number and chart here. Library versions are pinned and printed in the results header.
