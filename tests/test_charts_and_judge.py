import json

from extract_bench import build_corpus, charts, judge


def fake_summary():
    out = []
    for i, name in enumerate(["a", "b", "c"]):
        m = 0.9 - i * 0.2
        ci = {"mean": m, "lo": m - 0.05, "hi": m + 0.05, "n": 40}
        out.append({"extractor": name, "f1": ci, "recall": ci, "leak_rate": {"mean": 0.1 * i},
                    "latency_ms_median": 1.0 + i, "latency_ms_p90": 2.0 + i})
    return out


def test_charts_are_written(tmp_path):
    by_type = {s["extractor"]: {t: 0.5 for t in build_corpus.PAGE_TYPES} for s in fake_summary()}
    paths = charts.make_all(fake_summary(), by_type, {}, tmp_path)
    assert len(paths) == 4
    for p in paths:
        assert p.exists() and p.stat().st_size > 5000
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_judge_skips_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = judge.run(results_dir=tmp_path)
    assert res["skipped"] is True
    assert json.loads((tmp_path / "judge.json").read_text())["skipped"] is True


def test_metric_label_and_mock_judge():
    assert judge.metric_label({"f1": "0.85", "leak_rate": "0.1"}) == "GOOD"
    assert judge.metric_label({"f1": "0.85", "leak_rate": "0.5"}) == "BAD"
    assert judge.mock_judge("a b c d e", "a b c d e") == "GOOD"
    assert judge.mock_judge("a b c d e", "") == "BAD"


def test_parse_verdict():
    assert judge.parse_verdict("GOOD") == "GOOD"
    assert judge.parse_verdict(" bad.") == "BAD"
    assert judge.parse_verdict("NOT GOOD") == "BAD"
    assert judge.parse_verdict("") == "BAD"


def test_judge_survives_api_errors(tmp_path, monkeypatch):
    import csv as _csv

    gold = build_corpus.load_gold()[:3]
    with open(tmp_path / "outputs.jsonl", "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps({"extractor": "x", "doc_id": g["doc_id"], "title": None, "text": "t"}) + "\n")
    with open(tmp_path / "per_doc.csv", "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["extractor", "doc_id", "split", "f1", "leak_rate"])
        for g in gold:
            w.writerow(["x", g["doc_id"], "test", "0.9", "0.0"])
    calls = {"n": 0}

    def flaky(gold_text, out_text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("rate limited")
        return "GOOD"

    monkeypatch.setattr(judge, "pick_judge", lambda mock: ("fake", flaky))
    res = judge.run(n=3, results_dir=tmp_path)
    assert res["skipped"] is False and res["n"] == 2 and res["n_errors"] == 1
