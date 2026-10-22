from extract_bench import taxonomy as tx

CLEAN = {"error": None, "recall": 0.95, "precision": 0.95, "n_pred_tokens": 100, "leaked_kinds": [],
         "table_row_recall": None, "code_line_recall": None, "code_line_exact": None,
         "title_present": 1.0, "title_match": 1.0}


def row(**kw):
    r = dict(CLEAN)
    r.update(kw)
    return r


def test_clean_row_has_no_labels():
    assert tx.label(row()) == []


def test_crash_is_exclusive():
    assert tx.label(row(error="ValueError: x", recall=0.0)) == ["crash"]


def test_empty_and_low_recall():
    assert "empty_output" in tx.label(row(recall=0.0, n_pred_tokens=0))
    assert "low_recall" in tx.label(row(recall=0.5))


def test_over_extraction():
    assert "over_extraction" in tx.label(row(precision=0.4))


def test_leak_kinds_map_to_labels():
    labels = tx.label(row(leaked_kinds=["cookie", "nav", "script", "comment"]))
    assert {"consent_or_modal_leak", "nav_or_footer_leak", "script_or_noscript_leak",
            "comment_or_signature_leak"} <= set(labels)


def test_every_corpus_kind_has_a_label():
    from extract_bench import build_corpus as bc

    kinds = {b["kind"] for _, g in bc.build() for b in g["boilerplate"]}
    assert kinds <= set(tx.KIND_TO_LABEL), kinds - set(tx.KIND_TO_LABEL)


def test_table_and_code_rules():
    assert "table_lost" in tx.label(row(table_row_recall=0.25))
    assert "code_lost" in tx.label(row(code_line_recall=0.2, code_line_exact=0.0))
    assert "code_flattened" in tx.label(row(code_line_recall=1.0, code_line_exact=0.4))


def test_wrong_title_only_when_title_returned():
    assert "title_wrong" in tx.label(row(title_match=0.0))
    assert "title_wrong" not in tx.label(row(title_present=0.0, title_match=0.0))


def test_labels_come_in_fixed_order():
    labels = tx.label(row(recall=0.5, precision=0.4, title_match=0.0, leaked_kinds=["nav"]))
    assert labels == [lab for lab in tx.LABELS if lab in labels]
