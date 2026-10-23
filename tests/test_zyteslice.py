"""Tests for the Zyte external-gold slice loader. No network: HTTP is faked and the data is made up."""

import gzip
import json

import pytest

from extract_bench import metrics, zyteslice as z

HTML_A = "<html><body><nav>Home About</nav><article><p>First paragraph of the story.</p><p>Second one.</p></article></body></html>"
HTML_B = "<html><body><div><p>Other site story text here.</p></div></body></html>"
GT = {
    "aaa": {"articleBody": "First paragraph of the story.\n\nSecond  one. ", "url": "https://www.example.com/a"},
    "bbb": {"articleBody": "Other site story text here.", "url": "https://news.example.org/b?x=1"},
    "ccc": {"articleBody": "  \n\n ", "url": "https://example.com/c"},
}
HTMLS = {"aaa": HTML_A, "bbb": HTML_B, "ccc": "<p>x</p>"}


class FakeFetcher:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        if url.endswith("ground-truth.json"):
            return json.dumps(GT).encode("utf-8")
        item = url.rsplit("/", 1)[1].removesuffix(".html.gz")
        return gzip.compress(HTMLS[item].encode("utf-8"))


def test_site_of_strips_www_and_lowercases():
    assert z.site_of("https://WWW.Example.com/a/b") == "example.com"
    assert z.site_of("https://news.example.org/b?x=1") == "news.example.org"
    assert z.site_of("not a url") == ""


def test_normalise_body_collapses_and_drops_empty_lines():
    out = z.normalise_body("First  paragraph. \n\n\n  Second​ one.\n \n")
    assert out == ["First paragraph.", "Second one."]
    assert z.normalise_body("") == []
    assert z.normalise_body(None) == []


def test_gold_record_has_the_shape_metrics_expect():
    rec = z.gold_record("aaa", "https://www.example.com/a", ["First paragraph of the story."])
    assert rec["doc_id"] == "zyte-aaa" and rec["page_type"] == "example.com"
    assert rec["boilerplate"] == [] and rec["table_rows"] == [] and rec["code_lines"] == []
    s = metrics.score({"title": "", "text": "First paragraph of the story."}, rec)
    assert s["f1"] == pytest.approx(1.0)


def test_decode_html_roundtrip():
    assert z.decode_html(gzip.compress("café".encode("utf-8"))) == "café"


def test_build_skips_empty_gold_and_writes_manifest(tmp_path):
    cache, manifest = tmp_path / "cache", tmp_path / "m" / "manifest.json"
    doc = z.build(FakeFetcher(), cache=cache, manifest=manifest)
    assert doc["n_items_in_source"] == 3 and doc["n_pages"] == 2 and doc["n_sites"] == 2
    assert doc["skipped"] == [{"id": "ccc", "reason": "empty gold"}]
    assert doc["pinned_commit"] == z.PIN_SHA and "MIT" in doc["licence"]
    on_disk = json.loads(manifest.read_text(encoding="utf-8"))
    assert [p["id"] for p in on_disk["pages"]] == ["aaa", "bbb"]
    text = manifest.read_text(encoding="utf-8")
    assert "First paragraph" not in text and "<article>" not in text  # no third-party text in the manifest


def test_fetch_uses_the_pinned_commit(tmp_path):
    f = FakeFetcher()
    z.fetch_all(f, cache=tmp_path / "c")
    assert f.urls and all(z.PIN_SHA in u for u in f.urls)
    assert len(f.urls) == 4  # ground truth + 3 html files


def test_load_slice_returns_gold_html_and_sites(tmp_path):
    cache, manifest = tmp_path / "cache", tmp_path / "manifest.json"
    z.build(FakeFetcher(), cache=cache, manifest=manifest)
    gold, htmls, sites, warns = z.load_slice(manifest=manifest, cache=cache)
    assert warns == []
    assert [g["doc_id"] for g in gold] == ["zyte-aaa", "zyte-bbb"]
    assert gold[0]["main"] == ["First paragraph of the story.", "Second one."]
    assert htmls["zyte-aaa"] == HTML_A
    assert sites == {"zyte-aaa": "example.com", "zyte-bbb": "news.example.org"}


def test_load_slice_refetches_when_cache_is_missing(tmp_path):
    cache, manifest = tmp_path / "cache", tmp_path / "manifest.json"
    z.build(FakeFetcher(), cache=cache, manifest=manifest)
    other = tmp_path / "fresh"
    with pytest.raises(FileNotFoundError):
        z.load_slice(manifest=manifest, cache=other)
    f = FakeFetcher()
    gold, _, _, _ = z.load_slice(manifest=manifest, cache=other, fetcher=f)
    assert len(gold) == 2 and f.urls


def test_load_slice_warns_when_data_changed(tmp_path):
    cache, manifest = tmp_path / "cache", tmp_path / "manifest.json"
    z.build(FakeFetcher(), cache=cache, manifest=manifest)
    z._paths(cache, "aaa").write_bytes(gzip.compress(b"<p>changed</p>"))
    gt = json.loads((cache / "ground-truth.json").read_text(encoding="utf-8"))
    gt["bbb"]["articleBody"] = "Different gold now."
    (cache / "ground-truth.json").write_text(json.dumps(gt), encoding="utf-8")
    _, _, _, warns = z.load_slice(manifest=manifest, cache=cache)
    assert any("html hash differs" in w for w in warns)
    assert any("gold hash differs" in w for w in warns)


def test_site_ci_resamples_sites_and_is_seeded():
    vals = [0.9, 0.9, 0.5, 0.5, 0.7]
    groups = ["a", "a", "b", "b", "c"]
    r1 = z._site_ci(vals, groups, iters=500)
    r2 = z._site_ci(vals, groups, iters=500)
    assert r1 == r2
    assert r1["n_groups"] == 3 and r1["mean"] == pytest.approx(0.7)
    assert r1["lo"] <= r1["mean"] <= r1["hi"]


def test_splice_replaces_only_its_own_section(tmp_path):
    p = tmp_path / "RESULTS.md"
    p.write_text("# R\n\ntop\n\n## Real-page check (Wikipedia)\n\nwiki body\n", encoding="utf-8")
    z.splice_into_results(p, z.SECTION_TITLE + "\n\nfirst\n")
    z.splice_into_results(p, z.SECTION_TITLE + "\n\nsecond\n")
    t = p.read_text(encoding="utf-8")
    assert t.count(z.SECTION_TITLE) == 1 and "second" in t and "first" not in t
    assert "wiki body" in t and "top" in t


def test_fetcher_sends_user_agent_and_retries(monkeypatch):
    import urllib.error
    calls = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def opener(req, timeout):
        calls.append(req.get_header("User-agent"))
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return Resp()

    monkeypatch.setattr(z.time, "sleep", lambda s: None)
    f = z.Fetcher(min_interval=0, opener=opener)
    assert f.get("https://example.com/x") == b"ok"
    assert len(calls) == 2 and calls[0] == z.USER_AGENT
