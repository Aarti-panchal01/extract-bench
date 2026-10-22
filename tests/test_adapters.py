import pytest

from extract_bench import adapters, run
from extract_bench.adapters._text import html_fragment_to_text

SAMPLE = """<!doctype html><html><head><title>Hello | Site</title></head><body>
<nav><a href="/">Home</a></nav><article><h1>Hello</h1>
<p>This is a fairly long paragraph about a city council that approved a new rail plan on Tuesday evening.
The members said the work would start in spring and that the line would carry far more riders than the old one,
which has been crowded at rush hour for many years and is often late in the winter months.</p>
<p>Another paragraph explains the budget, the timeline and the reactions from local business owners, who were
worried that the building work would keep customers away from their shops for most of the next two years.</p>
<pre><code>x = 1</code></pre></article><footer>Copyright</footer></body></html>"""


def _load_or_skip(spec):
    try:
        return adapters.load(spec)
    except adapters.UnavailableAdapter as e:
        pytest.skip(str(e))


@pytest.mark.parametrize("spec", adapters.ADAPTERS, ids=lambda s: s.name)
def test_adapter_contract(spec):
    out = _load_or_skip(spec)(SAMPLE)
    assert isinstance(out, dict) and set(out) >= {"title", "text"}
    assert isinstance(out["text"], str) and "council" in out["text"]
    assert out["title"] is None or isinstance(out["title"], str)


@pytest.mark.parametrize("spec", adapters.ADAPTERS, ids=lambda s: s.name)
def test_adapter_handles_empty_page(spec):
    fn = _load_or_skip(spec)
    try:
        out = fn("<html><body></body></html>")
    except Exception:
        return  # allowed: the runner records exceptions as failures
    assert isinstance(out["text"], str)


def test_versions_reported_for_all_packages():
    v = adapters.versions()
    for spec in adapters.ADAPTERS:
        assert spec.package in v


def test_fragment_to_text_keeps_blocks_and_indent():
    t = html_fragment_to_text("<div><p>a b</p><pre>def f():\n    return 1</pre>"
                              "<table><tr><td>x</td><td>y</td></tr></table></div>")
    assert "a b" in t and "    return 1" in t and "x | y" in t


def test_runner_records_exceptions_as_failures():
    def boom(html):
        raise ValueError("bad page")

    out, ms, err = run.run_one(boom, "<p>x</p>", repeats=3)
    assert err.startswith("ValueError") and out["text"] == "" and ms >= 0


def test_runner_flags_contract_violation():
    out, ms, err = run.run_one(lambda h: "just a string", "<p>x</p>", repeats=1)
    assert err.startswith("ContractError")


def test_best_config_options_are_bound():
    pytest.importorskip("trafilatura")
    from extract_bench.adapters import trafilatura_adapter as tfa

    fn = tfa.make_configured(include_comments=False)
    assert fn.options == {"include_comments": False}
