"""Tests for the Wikipedia real-page slice loader and normaliser. No network: HTTP is faked."""

import json

import pytest

from extract_bench import metrics, wikislice as w

EXTRACT = """Intro paragraph about the thing.  It has odd   spaces.

== History ==
First paragraph of history.

=== Early years ===
Early years text.

== See also ==
Some list that is not prose.

=== A subsection of see also ===
Also dropped.

== Legacy ==
Legacy text.

== References ==
Ref line one.
== External links ==
Link line.
"""


def test_normalise_keeps_prose_and_headings_drops_trailing_sections():
    out = w.normalise_extract(EXTRACT)
    assert out == ["Intro paragraph about the thing. It has odd spaces.", "History",
                   "First paragraph of history.", "Early years", "Early years text.", "Legacy", "Legacy text."]


def test_normalise_empty_and_none():
    assert w.normalise_extract("") == []
    assert w.normalise_extract(None) == []


def test_normalise_nfc_and_zero_width():
    out = w.normalise_extract("Café au​ lait")
    assert out == ["Café au lait"]


def test_sample_ids_deterministic_and_prefix_stable():
    a = w.sample_ids(5, 100)
    b = w.sample_ids(5, 100)
    c = w.sample_ids(5, 50)
    assert a == b and a[:50] == c
    assert len(set(a)) == 100
    assert all(1 <= i <= w.MAX_PAGEID for i in a)
    assert w.sample_ids(6, 10) != a[:10]


@pytest.mark.parametrize("page,ok", [
    ({"ns": 0, "length": 30000}, True),
    ({"ns": 0, "length": 100}, False),
    ({"ns": 0, "length": 10 ** 6}, False),
    ({"ns": 1, "length": 30000}, False),
    ({"ns": 0, "length": 30000, "redirect": True}, False),
    ({"ns": 0, "length": 30000, "pageprops": {"disambiguation": ""}}, False),
    ({"ns": 0, "length": 30000, "pageprops": {"wikibase_item": "Q1"}}, True),
    ({"missing": True}, False),
    ({"invalid": True}, False),
])
def test_candidate_filter(page, ok):
    assert w.candidate_ok(page) is ok


def test_gold_record_is_scorable_by_existing_metrics():
    rec = w.gold_record("Example", 7, ["alpha beta gamma delta", "epsilon zeta"])
    assert rec["doc_id"] == "wiki-7" and rec["boilerplate"] == []
    s = metrics.score({"title": "Example", "text": "Example\nalpha beta gamma delta\nepsilon zeta"}, rec)
    assert s["f1"] == pytest.approx(1.0)
    assert s["leak_rate"] == 0.0


def _write_manifest(tmp_path, html, gold_text, revid=11):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"{revid}.html").write_text(html, encoding="utf-8")
    (cache / f"{revid}.gold.txt").write_text(gold_text, encoding="utf-8")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"pages": [{"pageid": 3, "title": "T", "revid": revid,
                                          "html_sha256": w.sha256(html), "gold_sha256": w.sha256(gold_text)}]}))
    return man, cache


def test_load_slice_from_cache_needs_no_client(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>x</html>", "one\ntwo")
    gold, htmls, warns = w.load_slice(man, cache)
    assert warns == []
    assert gold[0]["main"] == ["one", "two"] and gold[0]["title"] == "T"
    assert htmls["wiki-3"] == "<html>x</html>"


def test_load_slice_reports_hash_mismatch(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>x</html>", "one\ntwo")
    (cache / "11.html").write_text("<html>changed</html>", encoding="utf-8")
    _, _, warns = w.load_slice(man, cache)
    assert len(warns) == 1 and "html hash differs" in warns[0]


def test_load_slice_missing_cache_without_client_raises(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>x</html>", "one")
    (cache / "11.html").unlink()
    with pytest.raises(FileNotFoundError):
        w.load_slice(man, cache)


class FakeClient:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return "<html>fresh</html>"

    def api(self, **params):
        self.urls.append(params)
        return {"query": {"pages": [{"pageid": 3, "title": "T", "lastrevid": 11, "extract": "a b\n\n== Notes ==\nz"}]}}


def test_load_slice_refetches_missing_files_by_revision(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>fresh</html>", "a b")
    (cache / "11.html").unlink()
    (cache / "11.gold.txt").unlink()
    c = FakeClient()
    gold, htmls, warns = w.load_slice(man, cache, client=c)
    assert any(isinstance(u, str) and "oldid=11" in u for u in c.urls)
    assert gold[0]["main"] == ["a b"] and warns == []


def test_load_slice_warns_when_current_revision_moved(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>fresh</html>", "a b")
    (cache / "11.gold.txt").unlink()

    class Moved(FakeClient):
        def api(self, **p):
            r = super().api(**p)
            r["query"]["pages"][0]["lastrevid"] = 12
            return r

    _, _, warns = w.load_slice(man, cache, client=Moved(), verify=False)
    assert any("differs from pinned" in x for x in warns)


def test_client_sets_user_agent_and_rate_limits():
    seen = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def opener(req, timeout):
        seen.append(req)
        return Resp()

    c = w.Client(min_interval=0.2, opener=opener)
    import time
    t0 = time.monotonic()
    c.get("https://example.org/a")
    c.get("https://example.org/b")
    assert time.monotonic() - t0 >= 0.15
    assert all(r.get_header("User-agent") == w.USER_AGENT for r in seen)
    assert "extract-bench" in w.USER_AGENT


def test_spearman_and_ranks():
    assert w.spearman([3, 2, 1], [30, 20, 10]) == pytest.approx(1.0)
    assert w.spearman([3, 2, 1], [10, 20, 30]) == pytest.approx(-1.0)
    assert w._ranks([5, 5, 1]) == [1.5, 1.5, 3.0]


def test_section_md_and_splice(tmp_path):
    ci = {"mean": 0.5, "lo": 0.4, "hi": 0.6}
    res = {"n_pages": 2, "bootstrap_iters": 10,
           "summary": [{"extractor": "a", "f1": ci, "precision": ci, "recall": ci, "latency_ms_median": 3.0, "n_docs": 2}],
           "taxonomy_counts": {"a": {}}, "paired": {"top": "a", "vs_top": {}},
           "rank_vs_synthetic": {"synthetic_order": ["a"], "real_order": ["a"], "spearman_all_7": 1.0, "spearman_base_6": 1.0}}
    sec = w.section_md(res)
    assert sec.startswith(w.SECTION_TITLE) and "\u2014" not in sec and "\u2013" not in sec
    p = tmp_path / "RESULTS.md"
    p.write_text("# Results\n\nbody\n", encoding="utf-8")
    w.splice_into_results(p, sec)
    w.splice_into_results(p, sec)  # idempotent
    text = p.read_text(encoding="utf-8")
    assert text.count(w.SECTION_TITLE) == 1 and text.startswith("# Results")


def test_normalise_keep_back_matter_variant():
    out = w.normalise_extract(EXTRACT, drop_sections=False)
    assert "See also" in out and "Some list that is not prose." in out and "Link line." in out
    assert "References" in out


def test_load_slice_back_matter_variant_uses_raw_extract(tmp_path):
    man, cache = _write_manifest(tmp_path, "<html>x</html>", "one")
    (cache / "11.extract.txt").write_text("one\n\n== See also ==\nlist item\n", encoding="utf-8")
    gold, _, _ = w.load_slice(man, cache, keep_back_matter=True)
    assert gold[0]["main"] == ["one", "See also", "list item"]
