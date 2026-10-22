import pytest

from extract_bench import metrics as m


def test_tokens_lowercase_and_split_on_punctuation_and_underscore():
    assert m.tokens("Hello, World! send_welcome(user_id)") == ["hello", "world", "send", "welcome", "user", "id"]


def test_tokens_keep_devanagari_vowel_signs_together():
    assert m.tokens("नई योजना।") == ["नई", "योजना"]


def test_markdown_links_reduce_to_visible_text():
    assert m.tokens("[Read more](/story/123) and ![a cat](http://x.io/c.png)") == ["read", "more", "and", "a", "cat"]


def test_prf_hand_computed():
    # pred: a a b c   gold: a b b d -> overlap a(1)+b(1)=2; P=2/4, R=2/4
    p, r, f = m.prf(["a", "a", "b", "c"], ["a", "b", "b", "d"])
    assert (p, r) == (0.5, 0.5)
    assert f == pytest.approx(0.5)


def test_prf_asymmetric_hand_computed():
    # pred: x y   gold: x y z w -> P=1, R=0.5, F1=2/3
    p, r, f = m.prf(["x", "y"], ["x", "y", "z", "w"])
    assert p == 1.0 and r == 0.5 and f == pytest.approx(2 / 3)


def test_prf_empty_prediction_is_zero():
    assert m.prf([], ["a"]) == (0.0, 0.0, 0.0)


def test_contains_run():
    assert m.contains_run(list("abcde"), list("bcd"))
    assert not m.contains_run(list("abcde"), list("bd"))
    assert not m.contains_run(list("ab"), [])


def test_remove_title_only_near_start():
    t = ["big", "news"]
    assert m.remove_title(["big", "news", "body"], t) == ["body"]
    late = ["x"] * 100 + ["big", "news"]
    assert m.remove_title(late, t, window=60) == late


def test_title_in_body_is_neutral():
    gold = {"title": "Big news today", "main": ["the body text is here"], "boilerplate": []}
    with_title = m.score({"title": None, "text": "Big news today\nthe body text is here"}, gold)
    without = m.score({"title": None, "text": "the body text is here"}, gold)
    assert with_title["f1"] == without["f1"] == 1.0


def test_leak_detected_and_not_detected():
    gold_toks = m.tokens("the council approved the plan on monday")
    bp = [{"kind": "cookie", "text": "we use cookies to improve your experience"}]
    leaked = m.leak_details(m.tokens("the council approved. We use cookies to improve your experience"), bp, gold_toks)
    clean = m.leak_details(m.tokens("the council approved the plan"), bp, gold_toks)
    assert leaked[0]["leaked"] and not clean[0]["leaked"]


def test_leak_ignores_ngrams_shared_with_gold():
    # a snippet made only of gold n-grams cannot be scored as a leak
    gold_toks = m.tokens("one two three four five")
    bp = [{"kind": "related", "text": "one two three four"}]
    d = m.leak_details(gold_toks, bp, gold_toks)
    assert d[0]["scorable"] is False and d[0]["leaked"] is False


def test_leak_rate_in_score():
    gold = {"title": "T", "main": ["alpha beta gamma delta epsilon"],
            "boilerplate": [{"kind": "nav", "text": "home world business sports opinion"},
                            {"kind": "footer", "text": "copyright twenty twenty six all rights"}]}
    s = m.score({"title": None, "text": "alpha beta gamma delta epsilon home world business sports opinion"}, gold)
    assert s["leak_rate"] == 0.5 and s["leaked_kinds"] == ["nav"]


def test_table_row_recall():
    rows = ["Memory 16 GB", "Weight 1.2 kg"]
    assert m.run_recall(m.tokens("Memory | 16 GB\nWeight 9 kg"), rows) == 0.5
    assert m.run_recall([], []) is None


def test_code_exact_requires_indentation():
    code = ["def f():", "    return 1"]
    assert m.code_exact("def f():\n    return 1", code) == 1.0
    assert m.code_exact("def f():\nreturn 1", code) == 0.5  # flattened indentation


def test_code_exact_accepts_markdown_indented_block():
    code = ["def f():", "    return 1"]
    assert m.code_exact("    def f():\n        return 1", code) == 1.0


def test_score_title_match_and_fields():
    gold = {"title": "Lemon Pie", "main": ["mix the lemon"], "boilerplate": [], "table_rows": [], "code_lines": []}
    s = m.score({"title": "lemon pie", "text": "mix the lemon"}, gold)
    assert s["title_match"] == 1.0 and s["f1"] == 1.0 and s["leak_rate"] == 0.0
    s2 = m.score({"title": "Lemon Pie | Site", "text": ""}, gold)
    assert s2["title_match"] == 0.0 and s2["f1"] == 0.0
    assert s2["table_row_recall"] is None and s2["code_line_exact"] is None
