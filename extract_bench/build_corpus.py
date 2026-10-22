"""Build the seeded synthetic corpus: 10 page types x 6 variants = 60 HTML fixtures.

Every fixture is generated together with its gold record, so the gold is known
by construction instead of being labelled after the fact:

- main: the text a reader would call "the content", in reading order
- boilerplate: snippets that are NOT content (nav, cookie text, related links,
  comments, script payloads ...), each tagged with a kind
- table_rows / code_lines: structures whose survival we measure separately
- title: the visible h1 (the <title> tag deliberately adds " | Site Name")

Run: python -m extract_bench.build_corpus
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import textbanks as tb

SEED = 20261023
PAGE_TYPES = [
    "news",
    "blog_comments",
    "docs_code",
    "product_spec",
    "forum",
    "recipe",
    "listing",
    "cookie_modal",
    "nested_div",
    "non_english",
]
VARIANTS = 6
DEV_PER_TYPE = 2  # 2 dev + 4 test per type -> 20 dev / 40 test

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"


def esc(s: str) -> str:
    return htmllib.escape(s, quote=False)


@dataclass
class Page:
    doc_id: str
    page_type: str
    variant: int
    rng: random.Random
    lang: str = "en"
    title: str = ""
    site: str = ""
    main: list[str] = field(default_factory=list)
    boilerplate: list[dict] = field(default_factory=list)
    table_rows: list[str] = field(default_factory=list)
    code_lines: list[str] = field(default_factory=list)
    traps: set[str] = field(default_factory=set)
    semantic: bool = True

    # ---- helpers that emit HTML and record gold at the same time ----
    def cls(self) -> str:
        return f"c-{self.rng.randrange(16 ** 4):04x}"

    def para(self, text: str, tag: str = "p", link: bool = False) -> str:
        self.main.append(text)
        if link and len(text.split()) > 8:
            words = text.split()
            i = self.rng.randrange(1, len(words) - 4)
            j = i + self.rng.randint(2, 3)
            href = f"/topics/{words[i].lower().strip('.,')}"
            inner = (
                esc(" ".join(words[:i]))
                + f' <a href="{href}">'
                + esc(" ".join(words[i:j]))
                + "</a> "
                + esc(" ".join(words[j:]))
            )
            return f"<{tag}>{inner}</{tag}>"
        return f"<{tag}>{esc(text)}</{tag}>"

    def heading(self, text: str, level: int = 2) -> str:
        self.main.append(text)
        return f"<h{level}>{esc(text)}</h{level}>"

    def bp(self, kind: str, text: str, tag: str = "p", attrs: str = "") -> str:
        self.boilerplate.append({"kind": kind, "text": text})
        self.traps.add(kind)
        return f"<{tag}{attrs}>{esc(text)}</{tag}>"

    def bp_list(self, kind: str, items: list[str], href_prefix: str = "/") -> str:
        """A link list (nav, footer links, breadcrumbs). Recorded as one snippet."""
        self.boilerplate.append({"kind": kind, "text": " ".join(items)})
        self.traps.add(kind)
        lis = "".join(
            f'<li><a href="{href_prefix}{i.lower().replace(" ", "-")}">{esc(i)}</a></li>' for i in items
        )
        return f"<ul>{lis}</ul>"

    def table(self, header: list[str], rows: list[list[str]]) -> str:
        self.traps.add("table")
        th = "".join(f"<th>{esc(h)}</th>" for h in header)
        body = []
        for r in [header] + rows:
            self.table_rows.append(" ".join(r))
        self.main.append(" ".join(header))
        for r in rows:
            self.main.append(" ".join(r))
            body.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>")
        return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    def code(self, lines: list[str], lang: str = "python") -> str:
        self.traps.add("code")
        for ln in lines:
            if ln.strip():
                self.main.append(ln)
                self.code_lines.append(ln)
        body = esc("\n".join(lines))
        return f'<pre><code class="language-{lang}">{body}</code></pre>'

    def gold(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "page_type": self.page_type,
            "variant": self.variant,
            "lang": self.lang,
            "title": self.title,
            "main": self.main,
            "boilerplate": self.boilerplate,
            "table_rows": self.table_rows,
            "code_lines": self.code_lines,
            "traps": sorted(self.traps),
            "semantic": self.semantic,
        }


# ---------------------------------------------------------------- generators

def sentence(rng: random.Random, bank: dict) -> str:
    return f"{rng.choice(bank['subj'])} {rng.choice(bank['verb'])} {rng.choice(bank['obj'])} {rng.choice(bank['tail'])}."


def paragraphs(rng: random.Random, bank: dict, n_min: int, n_max: int) -> list[str]:
    out = []
    seen = set()
    for _ in range(rng.randint(n_min, n_max)):
        sents = []
        for _ in range(rng.randint(2, 4)):
            s = sentence(rng, bank)
            tries = 0
            while s in seen and tries < 20:
                s = sentence(rng, bank)
                tries += 1
            seen.add(s)
            sents.append(s)
        out.append(" ".join(sents))
    return out


def wrap(pg: Page, tag: str, inner: str, role: str = "") -> str:
    """Semantic tag in semantic pages, an obfuscated div otherwise."""
    if pg.semantic:
        return f"<{tag}>{inner}</{tag}>"
    r = f' data-r="{role}"' if role else ""
    return f'<div class="{pg.cls()}"{r}>{inner}</div>'


def nav(pg: Page, items: list[str] | None = None) -> str:
    items = items or ["Home", "World", "Business", "Technology", "Science", "Sports", "Opinion"]
    return wrap(pg, "nav", pg.bp_list("nav", items))


def footer(pg: Page) -> str:
    inner = pg.bp("footer", f"Copyright 2026 {pg.site} Media Group, all rights reserved worldwide.")
    inner += pg.bp_list("footer_links", ["Privacy policy", "Terms of use", "Contact us", "Careers", "Advertise with us"])
    return wrap(pg, "footer", inner)


def script_payload(pg: Page) -> str:
    exp = pg.rng.choice(["checkout flow variant", "homepage hero layout", "paywall meter test"])
    text = f"window app state page type article experiment {exp} visitor segment anonymous reader"
    pg.boilerplate.append({"kind": "script", "text": text})
    pg.traps.add("script")
    js = (
        "window.__APP_STATE__ = "
        + json.dumps({"page": "type article", "experiment": exp, "visitor": "segment anonymous reader"})
        + ";"
    )
    return f"<script>{js}</script>"


def noscript(pg: Page) -> str:
    return "<noscript>" + pg.bp(
        "noscript", "Please enable JavaScript in your browser settings to load comments, maps and interactive charts on this page."
    ) + "</noscript>"


def cookie_banner(pg: Page, lines: list[str] | None = None) -> str:
    lines = lines or tb.COOKIE_LINES
    inner = "".join(pg.bp("cookie", ln) for ln in lines)
    inner += '<button>Accept all</button><button>Manage preferences</button>'
    return f'<div class="{"cookie-consent" if pg.semantic else pg.cls()}" role="dialog">{inner}</div>'


def modal(pg: Page) -> str:
    inner = "<h2>Never miss a story</h2>" + "".join(pg.bp("modal", ln) for ln in tb.MODAL_LINES)
    inner += '<form><input type="email" placeholder="Email address"><button>Subscribe</button></form>'
    return f'<div class="{"newsletter-modal" if pg.semantic else pg.cls()}" aria-modal="true">{inner}</div>'


def related(pg: Page, bank: dict, n: int = 3, label: str = "Related articles") -> str:
    items = []
    for _ in range(n):
        teaser = sentence(pg.rng, bank)
        head = pg.rng.choice(tb.POPULAR)
        pg.boilerplate.append({"kind": "related", "text": f"{head} {teaser}"})
        items.append(f'<li><a href="/story/{pg.rng.randrange(10**6)}">{esc(head)}</a><p>{esc(teaser)}</p></li>')
    pg.traps.add("related")
    cls = "related" if pg.semantic else pg.cls()
    return f'<div class="{cls}"><h3>{esc(label)}</h3><ul>{"".join(items)}</ul></div>'


def sidebar(pg: Page) -> str:
    bio = pg.bp("sidebar", pg.rng.choice(tb.SIDEBAR_BIO))
    picks = pg.rng.sample(tb.POPULAR, 3)
    pop = pg.bp_list("popular", picks, href_prefix="/popular/")
    return wrap(pg, "aside", f"<h3>Popular this week</h3>{pop}{bio}", "side")


def share(pg: Page) -> str:
    return pg.bp("share", "Share this story on Facebook, X, LinkedIn or by email with a friend.", "div",
                 ' class="share"' if pg.semantic else f' class="{pg.cls()}"')


def head(pg: Page, extra: str = "") -> str:
    return (
        f'<!doctype html><html lang="{pg.lang}"><head><meta charset="utf-8">'
        f"<title>{esc(pg.title)} | {esc(pg.site)}</title>"
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>.{pg.cls()}{{display:flex}} body{{font-family:sans-serif}}</style>"
        f"{extra}</head>"
    )


def page_html(pg: Page, body_parts: list[str]) -> str:
    return head(pg, script_payload(pg)) + "<body>" + "".join(body_parts) + "</body></html>"


def h1(pg: Page) -> str:
    return f"<h1>{esc(pg.title)}</h1>"


# ---------------------------------------------------------------- page types

def build_news(pg: Page) -> str:
    bank = tb.NEWS
    pg.title = f"{pg.rng.choice(bank['subj'])} {pg.rng.choice(bank['verb'])} {pg.rng.choice(bank['obj'])}"
    body = [h1(pg), f'<p class="byline"><time datetime="2026-03-{pg.variant + 10}">March {pg.variant + 10}, 2026</time></p>']
    paras = paragraphs(pg.rng, bank, 4, 8)
    for i, ptext in enumerate(paras):
        body.append(pg.para(ptext, link=(i % 2 == 1)))
        if i == 1:
            q = (f'"We have waited a long time for this," said {pg.rng.choice(bank["name"])}, '
                 f'{pg.rng.choice(bank["role"])} who {pg.rng.choice(bank["detail"])}.')
            body.append(pg.para(q, tag="blockquote"))
        if i == len(paras) // 2:
            # related block placed INSIDE the article body: classic trap
            body.append(related(pg, bank))
    body.append(share(pg))
    article = wrap(pg, "article", "".join(body), "story")
    parts = [nav(pg)]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(wrap(pg, "main", article))
    if pg.variant >= 2:
        parts.append(sidebar(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_blog(pg: Page) -> str:
    bank = tb.BLOG
    pg.title = pg.rng.choice(bank["subj"]) + " " + pg.rng.choice(["taught me a lot", "was harder than I expected",
                                                                  "changed my mornings", "is worth trying"])
    body = [h1(pg)]
    for i, ptext in enumerate(paragraphs(pg.rng, bank, 4, 7)):
        if i == 2:
            body.append(pg.heading(pg.rng.choice(["What I would do differently", "The numbers", "A small surprise"])))
        body.append(pg.para(ptext, link=(i == 0)))
    article = wrap(pg, "article", "".join(body), "post")
    comments = []
    n = pg.rng.randint(3, 6)
    for line in pg.rng.sample(tb.COMMENT_LINES, n):
        who = pg.rng.choice(tb.FORUM["user"])
        pg.boilerplate.append({"kind": "comment", "text": line})
        pg.traps.add("comment")
        comments.append(f'<li class="comment"><span class="author">{esc(who)}</span><p>{esc(line)}</p></li>')
    csec = f'<section id="comments"><h3>{n} comments</h3><ol>{"".join(comments)}</ol></section>'
    parts = [nav(pg, ["Home", "Archive", "About", "Newsletter", "Contact"])]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(wrap(pg, "main", article + csec))
    if pg.variant >= 3:
        parts.append(sidebar(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def docs_code_lines(rng: random.Random, variant: int) -> list[list[str]]:
    qname = rng.choice(["emails", "thumbnails", "invoices", "reports"])
    workers = rng.choice([2, 4, 8])
    block1 = [
        "from fastqueue import Queue, RetryPolicy",
        "",
        f'queue = Queue(name="{qname}", workers={workers})',
        "policy = RetryPolicy(max_retries=5, backoff_seconds=2)",
    ]
    block2 = [
        "def send_welcome(user_id, *args, **kwargs):",
        "    attempts = 0",
        "    while attempts < policy.max_retries:",
        "        if deliver(user_id) and not kwargs.get(\"dry_run\"):",
        "            return True",
        "        attempts += 1",
        "    return False",
    ]
    block3 = [
        f"$ fastqueue worker --queue {qname} --concurrency {workers}",
        "$ fastqueue status --format json > status.json",
    ]
    return [block1, block2, block3][: 2 + (variant % 2)]


def build_docs(pg: Page) -> str:
    bank = tb.DOCS
    pg.title = pg.rng.choice(["Getting started with retries", "Configuring workers", "Scheduling jobs",
                              "Handling failed tasks"])
    blocks = docs_code_lines(pg.rng, pg.variant)
    body = [h1(pg)]
    sections = ["Installation", "Configuration", "Usage", "Troubleshooting"][: len(blocks) + 1]
    paras = paragraphs(pg.rng, bank, len(sections) + 1, len(sections) + 3)
    for i, sec in enumerate(sections):
        body.append(pg.heading(sec))
        body.append(pg.para(paras[i], link=(i == 1)))
        if i < len(blocks):
            body.append(pg.code(blocks[i], "bash" if blocks[i][0].startswith("$") else "python"))
    for ptext in paras[len(sections):]:
        body.append(pg.para(ptext))
    if pg.variant >= 3:
        body.append(pg.heading("Options"))
        body.append(pg.table(["Option", "Default", "Description"], [
            ["max_retries", "3", "How many times a task is retried"],
            ["backoff_seconds", "1", "Wait between attempts"],
            ["visibility_timeout", "30", "Seconds before a task is redelivered"],
        ]))
    toc = wrap(pg, "nav", "<h4>On this page</h4>" + pg.bp_list("toc", ["On this page"] + sections, "#"), "toc")
    fb = pg.bp("feedback", "Was this page helpful? Tell us how we can improve the docs. Edit this page on GitHub.",
               "div")
    side = wrap(pg, "aside", pg.bp_list("doc_nav", ["Introduction", "Quickstart", "Concepts", "API reference",
                                                     "Changelog", "Community"], "/docs/"), "docnav")
    parts = [nav(pg, ["Docs", "Blog", "Pricing", "GitHub", "Status"]), side, wrap(pg, "main", wrap(pg, "article", "".join(body)) + fb), toc]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_product(pg: Page) -> str:
    bank = tb.PRODUCT
    model = pg.rng.choice(["Aero 14", "Nimbus Pro", "Vector X2", "Lumen Air"])
    pg.title = f"{model} laptop, {pg.rng.choice(['2026 edition', 'creator edition', 'business edition'])}"
    cores = pg.rng.choice([8, 10, 12])
    ram = pg.rng.choice([16, 24, 32])
    rows = [
        ["Processor", f"{cores}-core 3.{pg.rng.randint(1, 8)} GHz"],
        ["Memory", f"{ram} GB LPDDR5"],
        ["Storage", f"{pg.rng.choice([512, 1024])} GB NVMe SSD"],
        ["Display", "14 inch 2880 x 1800 OLED, 120 Hz"],
        ["Battery", f"{pg.rng.choice([60, 72, 80])} Wh, up to {pg.rng.randint(14, 22)} hours"],
        ["Weight", f"1.{pg.rng.randint(10, 45)} kg"],
        ["Ports", "2 x USB-C, 1 x HDMI 2.1, headphone jack"],
    ]
    crumbs = wrap(pg, "nav", pg.bp_list("breadcrumb", ["Home", "Electronics", "Laptops", "Ultrabooks"]), "crumbs")
    body = [crumbs, h1(pg)]
    body.append(f'<div class="price">USD {pg.rng.randint(9, 19)}99</div>')
    body.append(pg.bp("commerce", "Add to cart now and get free delivery on orders over fifty dollars, returns within thirty days.", "div"))
    for i, ptext in enumerate(paragraphs(pg.rng, bank, 2, 4)):
        body.append(pg.para(ptext, link=(i == 0)))
    body.append(pg.heading("Technical specifications"))
    body.append(pg.table(["Feature", "Detail"], rows))
    if pg.variant % 2 == 0:
        # spec table without <thead>, inside layout divs: a common shop pattern
        body[-1] = body[-1].replace("<thead>", "").replace("</thead>", "")
    also = related(pg, bank, n=3, label="Customers also bought")
    parts = [nav(pg, ["Shop", "Deals", "New arrivals", "Support", "Account"]),
             wrap(pg, "main", wrap(pg, "article", "".join(body)) + also)]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_forum(pg: Page) -> str:
    bank = tb.FORUM
    first = sentence(pg.rng, bank)
    pg.title = first.split(" when ")[0].split(" whenever ")[0].split(" after ")[0].split(" if ")[0].rstrip(".")
    pg.title = pg.title.replace("My ", "").replace("The ", "").capitalize() + " problem, need advice"
    rules = pg.bp("sidebar", "Forum rules: be kind to newcomers, stay on topic and search the archive before posting a new thread.",
                  "div")
    posts = []
    users = pg.rng.sample(bank["user"], pg.rng.randint(3, 5))
    for k, user in enumerate(users):
        if k == 0:
            text = first + " " + sentence(pg.rng, bank)
        else:
            text = pg.rng.choice(bank["reply_open"]) + " " + sentence(pg.rng, bank)
        inner = f'<div class="user">{esc(user)}</div>'
        pg.main.append(user)
        inner += pg.para(text)
        if k % 2 == 1:
            sig = pg.rng.choice(tb.SIGNATURES)
            pg.boilerplate.append({"kind": "signature", "text": sig})
            pg.traps.add("signature")
            inner += f'<div class="signature">{esc(sig)}</div>'
        inner += '<div class="actions"><a href="#">Reply</a> <a href="#">Quote</a> <a href="#">Report</a></div>'
        posts.append(f'<div class="post" id="p{k}">{inner}</div>')
    thread = h1(pg) + "".join(posts)
    parts = [nav(pg, ["Forums", "New posts", "Members", "Marketplace", "Search"]), rules,
             wrap(pg, "main", thread)]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    if pg.variant >= 3:
        parts.append(sidebar(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_recipe(pg: Page) -> str:
    bank = tb.RECIPE
    pg.title = bank["dish"][pg.variant % len(bank["dish"])]
    body = [h1(pg)]
    body.append(pg.bp("ui", "Jump to recipe, print recipe or save it to your favourites for later.", "div"))
    intro = pg.rng.sample(bank["intro"], 3)
    body.append(pg.para(" ".join(intro[:2])))
    body.append(pg.bp("ad", "Advertisement: try our partner meal kits with twenty percent off your first box this month.", "div",
                      ' class="ad-slot"'))
    body.append(pg.para(intro[2]))
    body.append(pg.heading("Ingredients"))
    ings = pg.rng.sample(bank["ingredient"], pg.rng.randint(6, 9))
    body.append("<ul>" + "".join(pg.para(i, tag="li") for i in ings) + "</ul>")
    body.append(pg.heading("Method"))
    steps = bank["step"][: pg.rng.randint(5, 7)]
    body.append("<ol>" + "".join(pg.para(s, tag="li") for s in steps) + "</ol>")
    if pg.variant >= 3:
        body.append(pg.heading("Nutrition per serving"))
        body.append(pg.table(["Calories", "Protein", "Carbs", "Fat"],
                             [[f"{pg.rng.randint(280, 520)} kcal", f"{pg.rng.randint(8, 30)} g",
                               f"{pg.rng.randint(20, 60)} g", f"{pg.rng.randint(6, 25)} g"]]))
    parts = [nav(pg, ["Recipes", "Quick dinners", "Baking", "Vegetarian", "Shop"]),
             wrap(pg, "main", wrap(pg, "article", "".join(body)))]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    if pg.variant % 2 == 0:
        lines = pg.rng.sample(tb.COMMENT_LINES, 2)
        for ln in lines:
            pg.boilerplate.append({"kind": "comment", "text": ln})
        pg.traps.add("comment")
        parts.append('<section class="reviews"><h3>Reviews</h3>' + "".join(f"<p>{esc(ln)}</p>" for ln in lines) + "</section>")
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_listing(pg: Page) -> str:
    bank = tb.LISTING
    cat = bank["category"][pg.variant % len(bank["category"])]
    pg.title = cat
    n = pg.rng.randint(12, 24)
    body = [h1(pg), pg.para(f"Showing {n} results in {cat.lower()}. Prices include tax and every order ships with free returns.")]
    cards = []
    for _ in range(n):
        name = f"{pg.rng.choice(bank['brand'])} {pg.rng.choice(bank['adj'])} {cat.rstrip('s').lower()}"
        price = f"USD {pg.rng.randint(19, 249)}.{pg.rng.choice(['00', '50', '99'])}"
        rating = f"{pg.rng.randint(30, 50) / 10} out of 5 stars from {pg.rng.randint(3, 900)} reviews"
        txt = f"{name} {price} {rating}"
        pg.boilerplate.append({"kind": "listing_item", "text": txt})
        cards.append(f'<li class="card"><a href="/p/{pg.rng.randrange(10**6)}">{esc(name)}</a>'
                     f'<span class="price">{esc(price)}</span><span class="rating">{esc(rating)}</span></li>')
    pg.traps.add("listing_item")
    filters = wrap(pg, "aside", pg.bp_list("filters", ["Filter by brand", "Price range", "Colour", "Size", "Customer rating"], "#"), "filters")
    pager = pg.bp_list("pagination", ["Previous page", "Page 1", "Page 2", "Page 3", "Next page"], "?p=")
    parts = [nav(pg, ["Shop", "Deals", "New arrivals", "Support", "Account"]), filters,
             wrap(pg, "main", "".join(body) + f'<ul class="grid">{"".join(cards)}</ul>' + pager)]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_cookie_modal(pg: Page) -> str:
    bank = tb.NEWS
    pg.title = f"{pg.rng.choice(bank['subj'])} {pg.rng.choice(bank['verb'])} {pg.rng.choice(bank['obj'])}"
    body = [h1(pg)]
    for i, ptext in enumerate(paragraphs(pg.rng, bank, 3, 6)):
        body.append(pg.para(ptext, link=(i == 2)))
    parts = [cookie_banner(pg), modal(pg), nav(pg), wrap(pg, "main", wrap(pg, "article", "".join(body)))]
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    if pg.variant % 2 == 1:
        parts.append(sidebar(pg))
    parts.append(footer(pg))
    if pg.variant >= 3:
        # some sites render the consent box at the end of <body>
        parts.append(parts.pop(0))
    return page_html(pg, parts)


def build_nested_div(pg: Page) -> str:
    bank = tb.NEWS if pg.variant % 2 == 0 else tb.BLOG
    pg.title = f"{pg.rng.choice(bank['subj'])} {pg.rng.choice(bank['verb'])} {pg.rng.choice(bank['obj'])}"
    pg.semantic = False
    texts = []
    for i, ptext in enumerate(paragraphs(pg.rng, bank, 4, 7)):
        pg.main.append(ptext)
        if pg.variant >= 3:
            # text split by <br><br> inside a single div, no block elements
            texts.append(esc(ptext) + "<br><br>")
        else:
            texts.append(f'<div class="{pg.cls()}">{esc(ptext)}</div>')
    inner = f'<div class="{pg.cls()}"><span class="{pg.cls()}">{esc(pg.title)}</span></div>' if pg.variant == 5 else h1(pg)
    if pg.variant == 5:
        # title is not in an h1 at all: only a styled span
        pass
    inner += f'<div class="{pg.cls()}">{"".join(texts)}</div>'
    for _ in range(pg.rng.randint(4, 6)):
        inner = f'<div class="{pg.cls()}">{inner}</div>'
    side_inner = (
        f'<div class="{pg.cls()}">' + pg.bp("sidebar", pg.rng.choice(tb.SIDEBAR_BIO), "div") + "</div>"
        + f'<div class="{pg.cls()}">' + "".join(
            pg.bp("popular", f"{t}. " + sentence(pg.rng, tb.BLOG if bank is tb.NEWS else tb.NEWS), "div")
            for t in pg.rng.sample(tb.POPULAR, 3)) + "</div>"
    )
    parts = [nav(pg), f'<div class="{pg.cls()}">{inner}</div>', f'<div class="{pg.cls()}">{side_inner}</div>']
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    parts.append(footer(pg))
    return page_html(pg, parts)


def build_non_english(pg: Page) -> str:
    lang = ["es", "de", "fr", "pt", "it", "hi"][pg.variant]
    pg.lang = lang
    L = tb.NON_ENGLISH[lang]
    pg.title = L["title"]
    sents = list(L["sents"])
    pg.rng.shuffle(sents)
    body = [h1(pg)]
    k = 0
    while k < len(sents):
        n = pg.rng.randint(2, 3)
        body.append(pg.para(" ".join(sents[k:k + n])))
        k += n
    body.append(pg.bp("related", L["related"], "div", ' class="related"'))
    parts = [nav(pg, L["nav"].split()), wrap(pg, "main", wrap(pg, "article", "".join(body)))]
    # override nav snippet text so it matches the language bank exactly
    parts.insert(0, f'<div class="{"cookie-consent" if pg.semantic else pg.cls()}">' + pg.bp("cookie", L["cookie"]) + "</div>")
    if pg.variant in (1, 4):
        parts.append(noscript(pg))
    foot = wrap(pg, "footer", pg.bp("footer", L["footer"]))
    parts.append(foot)
    return page_html(pg, parts)


BUILDERS = {
    "news": build_news,
    "blog_comments": build_blog,
    "docs_code": build_docs,
    "product_spec": build_product,
    "forum": build_forum,
    "recipe": build_recipe,
    "listing": build_listing,
    "cookie_modal": build_cookie_modal,
    "nested_div": build_nested_div,
    "non_english": build_non_english,
}


def assign_splits(seed: int = SEED) -> dict[str, str]:
    rng = random.Random(seed * 7 + 1)
    split = {}
    for t in PAGE_TYPES:
        idx = list(range(VARIANTS))
        rng.shuffle(idx)
        for k, v in enumerate(idx):
            split[f"{t}-{v}"] = "dev" if k < DEV_PER_TYPE else "test"
    return split


def build(seed: int = SEED) -> list[tuple[str, dict]]:
    """Return [(html, gold), ...] for all 60 fixtures. Pure function of seed."""
    split = assign_splits(seed)
    out = []
    for ti, t in enumerate(PAGE_TYPES):
        for v in range(VARIANTS):
            rng = random.Random(f"{seed}-{t}-{v}")
            doc_id = f"{t}-{v}"
            pg = Page(doc_id=doc_id, page_type=t, variant=v, rng=rng,
                      site=tb.SITES[(ti + v) % len(tb.SITES)])
            if t != "nested_div":
                pg.semantic = v % 2 == 0
            html = BUILDERS[t](pg)
            g = pg.gold()
            g["split"] = split[doc_id]
            g["sha1"] = hashlib.sha1(html.encode("utf-8")).hexdigest()
            out.append((html, g))
    return out


def write(out_dir: Path = CORPUS_DIR, seed: int = SEED) -> Path:
    out_dir = Path(out_dir)
    (out_dir / "html").mkdir(parents=True, exist_ok=True)
    items = build(seed)
    with open(out_dir / "gold.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for html, g in items:
            (out_dir / "html" / f"{g['doc_id']}.html").write_text(html, encoding="utf-8", newline="\n")
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return out_dir


def load_gold(corpus_dir: Path = CORPUS_DIR) -> list[dict]:
    with open(Path(corpus_dir) / "gold.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_html(doc_id: str, corpus_dir: Path = CORPUS_DIR) -> str:
    return (Path(corpus_dir) / "html" / f"{doc_id}.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    d = write()
    gold = load_gold(d)
    print(f"wrote {len(gold)} fixtures to {d}")
    print("dev:", sum(g["split"] == "dev" for g in gold), "test:", sum(g["split"] == "test" for g in gold))
