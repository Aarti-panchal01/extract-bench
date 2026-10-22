import html as htmllib
import re
from collections import Counter

import pytest

from extract_bench import build_corpus as bc
from extract_bench import metrics


@pytest.fixture(scope="module")
def items():
    return bc.build()


def test_sixty_fixtures_ten_types_six_variants(items):
    assert len(items) == 60
    c = Counter(g["page_type"] for _, g in items)
    assert set(c) == set(bc.PAGE_TYPES) and set(c.values()) == {6}
    assert len({g["doc_id"] for _, g in items}) == 60


def test_split_is_20_40_disjoint_and_stratified(items):
    dev = {g["doc_id"] for _, g in items if g["split"] == "dev"}
    test = {g["doc_id"] for _, g in items if g["split"] == "test"}
    assert len(dev) == 20 and len(test) == 40 and not dev & test
    per_type = Counter(g["page_type"] for _, g in items if g["split"] == "dev")
    assert set(per_type.values()) == {2}


def test_build_is_deterministic(items):
    again = bc.build()
    assert [g["sha1"] for _, g in items] == [g["sha1"] for _, g in again]


def test_files_on_disk_match_generator(items):
    if not (bc.CORPUS_DIR / "gold.jsonl").exists():
        pytest.skip("corpus not written yet")
    disk = {g["doc_id"]: g["sha1"] for g in bc.load_gold()}
    assert disk == {g["doc_id"]: g["sha1"] for _, g in items}


def _visible_tokens(html):
    return metrics.tokens(htmllib.unescape(re.sub(r"<[^>]+>", " ", html)))


def test_every_gold_unit_appears_in_its_page(items):
    for html, g in items:
        page = _visible_tokens(html)
        for unit in g["main"]:
            assert metrics.contains_run(page, metrics.tokens(unit)), (g["doc_id"], unit)


def test_boilerplate_is_not_part_of_gold_main(items):
    for _, g in items:
        main = "\n".join(g["main"])
        for b in g["boilerplate"]:
            assert b["text"] not in main, (g["doc_id"], b["text"])


def test_title_tag_adds_site_name_but_gold_title_is_h1(items):
    for html, g in items:
        title_tag = re.search(r"<title>(.*?)</title>", html).group(1)
        assert " | " in title_tag and " | " not in g["title"]


def test_traps_present_by_construction(items):
    by = {g["doc_id"]: g for _, g in items}
    for v in range(6):
        assert {"cookie", "modal"} <= set(by[f"cookie_modal-{v}"]["traps"])
        assert "code" in by[f"docs_code-{v}"]["traps"] and by[f"docs_code-{v}"]["code_lines"]
        assert "table" in by[f"product_spec-{v}"]["traps"]
        assert "related" in by[f"news-{v}"]["traps"]
        assert "comment" in by[f"blog_comments-{v}"]["traps"]
        assert by[f"nested_div-{v}"]["semantic"] is False
        assert "script" in by[f"news-{v}"]["traps"]
    assert {by[f"non_english-{v}"]["lang"] for v in range(6)} == {"es", "de", "fr", "pt", "it", "hi"}
    assert sum("noscript" in g["traps"] for _, g in items) >= 15


def test_listing_page_gold_is_small(items):
    for _, g in items:
        if g["page_type"] == "listing":
            assert len(metrics.tokens(" ".join(g["main"]))) < 40
            assert sum(b["kind"] == "listing_item" for b in g["boilerplate"]) >= 12
