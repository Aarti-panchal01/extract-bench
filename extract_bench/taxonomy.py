"""Rule-based failure labels for one (extractor, document) result.

Rules run in a fixed order and every matching label is kept, so one document
can fail in several ways at once. Thresholds are fixed constants, chosen before
looking at the test split.
"""

from __future__ import annotations

EMPTY_RECALL = 0.05
LOW_RECALL = 0.70
LOW_PRECISION = 0.70
TABLE_LOST = 0.5
CODE_LOST = 0.5

LABELS = [
    "crash",
    "empty_output",
    "low_recall",
    "over_extraction",
    "nav_or_footer_leak",
    "consent_or_modal_leak",
    "related_or_teaser_leak",
    "comment_or_signature_leak",
    "script_or_noscript_leak",
    "commerce_or_listing_leak",
    "table_lost",
    "code_lost",
    "code_flattened",
    "title_wrong",
]

KIND_TO_LABEL = {
    "nav": "nav_or_footer_leak",
    "footer": "nav_or_footer_leak",
    "footer_links": "nav_or_footer_leak",
    "breadcrumb": "nav_or_footer_leak",
    "toc": "nav_or_footer_leak",
    "doc_nav": "nav_or_footer_leak",
    "pagination": "nav_or_footer_leak",
    "filters": "nav_or_footer_leak",
    "cookie": "consent_or_modal_leak",
    "modal": "consent_or_modal_leak",
    "related": "related_or_teaser_leak",
    "popular": "related_or_teaser_leak",
    "sidebar": "related_or_teaser_leak",
    "share": "related_or_teaser_leak",
    "feedback": "related_or_teaser_leak",
    "comment": "comment_or_signature_leak",
    "signature": "comment_or_signature_leak",
    "script": "script_or_noscript_leak",
    "noscript": "script_or_noscript_leak",
    "commerce": "commerce_or_listing_leak",
    "listing_item": "commerce_or_listing_leak",
    "ad": "commerce_or_listing_leak",
    "ui": "commerce_or_listing_leak",
}


def label(result: dict) -> list[str]:
    """result: a scored row (metrics.score output plus 'error' and 'page_type')."""
    if result.get("error"):
        return ["crash"]
    out: list[str] = []
    r, p = result.get("recall", 0.0), result.get("precision", 0.0)
    if result.get("n_pred_tokens", 0) == 0 or r < EMPTY_RECALL:
        out.append("empty_output")
    elif r < LOW_RECALL:
        out.append("low_recall")
    if result.get("n_pred_tokens", 0) > 0 and p < LOW_PRECISION:
        out.append("over_extraction")
    for kind in result.get("leaked_kinds", []):
        lab = KIND_TO_LABEL.get(kind)
        if lab and lab not in out:
            out.append(lab)
    t = result.get("table_row_recall")
    if t is not None and t < TABLE_LOST:
        out.append("table_lost")
    cr, ce = result.get("code_line_recall"), result.get("code_line_exact")
    if cr is not None and cr < CODE_LOST:
        out.append("code_lost")
    elif ce is not None and cr is not None and ce < cr - 0.25:
        out.append("code_flattened")
    if result.get("title_present") and not result.get("title_match"):
        out.append("title_wrong")
    return [lab for lab in LABELS if lab in out]
