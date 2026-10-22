from extract_bench import demo, judge


def test_demo_scores_every_available_tool(capsys):
    assert demo.main(["cookie_modal-3", "--lines", "1"]) == 0
    out = capsys.readouterr().out
    assert "page: cookie_modal-3" in out
    assert "extractor" in out and "F1" in out
    for name in ("trafilatura", "readability-lxml", "bs4-naive"):
        assert f"--- {name}" in out


def test_demo_unknown_doc_is_an_error(capsys):
    assert demo.main(["no-such-page"]) == 2


def test_demo_on_own_html_has_no_scores(tmp_path, capsys):
    p = tmp_path / "p.html"
    p.write_text("<html><body><nav>Home</nav><article><h1>Hi</h1><p>Hello there friend.</p></article></body></html>")
    assert demo.main(["--html", str(p)]) == 0
    out = capsys.readouterr().out
    assert "no gold" in out and " F1 " not in out


def test_stratified_sample_is_balanced_and_seeded():
    rows = [{"extractor": e, "doc_id": f"d{i}"} for e in ("a", "b", "c") for i in range(10)]
    s1 = judge.stratified_sample(rows, 4, seed=1)
    s2 = judge.stratified_sample(rows, 4, seed=1)
    assert s1 == s2 and len(s1) == 12
    assert sorted({r["extractor"] for r in s1}) == ["a", "b", "c"]
    assert all(sum(r["extractor"] == e for r in s1) == 4 for e in "abc")


def test_summarize_confusion_and_per_extractor():
    items = [
        {"extractor": "a", "metric": "GOOD", "judge": "GOOD"},
        {"extractor": "a", "metric": "GOOD", "judge": "BAD"},
        {"extractor": "b", "metric": "BAD", "judge": "BAD"},
        {"extractor": "b", "metric": "BAD", "judge": "BAD"},
    ]
    s = judge.summarize(items)
    assert s["n"] == 4 and s["agreement"] == 0.75
    assert s["confusion"] == {"metric_GOOD_judge_GOOD": 1, "metric_GOOD_judge_BAD": 1,
                              "metric_BAD_judge_GOOD": 0, "metric_BAD_judge_BAD": 2}
    assert s["per_extractor"]["a"] == {"n": 2, "agree": 1, "metric_good": 2, "judge_good": 1}
    lo, hi = s["cohen_kappa_ci95"]
    assert -1.0 <= lo <= s["cohen_kappa"] <= hi <= 1.0


def test_groq_body_gives_reasoning_models_room():
    b = judge.groq_body("openai/gpt-oss-120b", "x")
    assert b["max_tokens"] >= 100 and b["reasoning_effort"] == "low" and b["temperature"] == 0
    assert judge.groq_body("qwen/qwen3.8-27b", "x")["reasoning_effort"] == "none"
    assert "reasoning_effort" not in judge.groq_body("some/other-model", "x")


def test_judge_report_compares_two_runs(tmp_path):
    import json

    from extract_bench import judge_report

    def run(labels, name):
        items = [{"extractor": "x", "doc_id": f"d{i}", "f1": 0.9, "leak_rate": 0.0,
                  "metric": "GOOD" if i % 2 else "BAD", "judge": lab} for i, lab in enumerate(labels)]
        r = {"skipped": False, "judge": "fake", "model": name, "seed": 7, "sampling": "test",
             "n_errors": 0, **judge.summarize(items), "items": items, "errors": []}
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(r))
        return p

    a = run(["BAD", "GOOD", "BAD", "GOOD"], "a")
    b = run(["BAD", "GOOD", "GOOD", "GOOD"], "b")
    skipped = tmp_path / "s.json"
    skipped.write_text(json.dumps({"skipped": True}))
    out = tmp_path / "J.md"
    assert judge_report.main([str(a), str(b), str(skipped), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "a vs b | 4 | 0.75" in md
    assert "All judges gave the same label on 3; the metric rule matches them on 3" in md
