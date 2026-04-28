from __future__ import annotations

from war_room.skills import (
    funnel_investigation,
    hypothesis_formation,
    investigation_summary,
    release_metric_correlation,
    source_routing,
)


# ---------------------------------------------------------------------------
# source_routing
# ---------------------------------------------------------------------------

def test_source_routing_detects_query_plan():
    text = "Sources to query (in order):\n1. pulse — check_metric(...)"
    assert source_routing.is_query_plan(text)
    assert not source_routing.is_gap_declaration(text)


def test_source_routing_detects_gap_declaration():
    text = "The question requires infrastructure metrics, which is not available"
    assert source_routing.is_gap_declaration(text)
    assert not source_routing.is_query_plan(text)


def test_source_routing_build_message_includes_question():
    msg = source_routing.build_message("Why did checkout drop?")
    assert "Why did checkout drop?" in msg["content"]
    assert msg["role"] == "user"


# ---------------------------------------------------------------------------
# funnel_investigation
# ---------------------------------------------------------------------------

_FUNNEL_FINDING = """
Metric: users_product_list/active
Window: 2026-04-14 to 2026-04-28
Coverage: complete

Findings:
- mx_android: drop of ~18% from rolling baseline starting 2026-04-22
- mx_ios: within normal range

Summary: Drop is Android-only, onset 2026-04-22, magnitude ~18%.
"""


def test_funnel_has_finding_true():
    assert funnel_investigation.has_finding(_FUNNEL_FINDING)


def test_funnel_has_finding_false():
    assert not funnel_investigation.has_finding("No metrics found.")


def test_funnel_extract_metric_names():
    names = funnel_investigation.extract_metric_names(_FUNNEL_FINDING)
    assert names == ["users_product_list/active"]


# ---------------------------------------------------------------------------
# release_metric_correlation
# ---------------------------------------------------------------------------

_RELEASE_FINDING = """
Time window: 2026-04-14 to 2026-04-28
Repositories queried: android
Coverage: complete

Candidate releases:
- android android-v4.12.1 (2026-04-21T14:30:00Z) — strong
  What changed: Cambios en layout de tarjetas de producto.
  Temporal reasoning: deployed 21h before metric onset on 2026-04-22.
"""

_REPO_GAP_FINDING = """
Time window: 2026-04-14 to 2026-04-28
Repositories queried: android
Coverage: partial — android not confirmed

Candidate releases:
- Not assessed — android not available: No confirmed repositories available.
"""


def test_release_has_finding_true():
    assert release_metric_correlation.has_finding(_RELEASE_FINDING)


def test_release_has_finding_gap_still_true():
    assert release_metric_correlation.has_finding(_REPO_GAP_FINDING)


def test_release_has_finding_false():
    assert not release_metric_correlation.has_finding("No release data.")


# ---------------------------------------------------------------------------
# hypothesis_formation
# ---------------------------------------------------------------------------

_HYPOTHESIS_TEXT = """
Hypothesis: The android v4.12.1 release caused a 18% drop in users_product_list/active on mx_android starting 2026-04-22.
Confidence: Working

Evidence for:
- Temporal overlap: android-v4.12.1 deployed 21h before onset.

Evidence against:
- Release-agent repositories not confirmed; no release data for backend.

What would confirm this:
- Confirm android repo in release-agent and retrieve release explanation.

What would refute this:
- If backend was also deployed in the same window and affected all platforms.

Next steps:
- Ask tech lead to confirm android repo in release-agent.
"""


def test_hypothesis_has_hypothesis_true():
    assert hypothesis_formation.has_hypothesis(_HYPOTHESIS_TEXT)


def test_hypothesis_has_hypothesis_false():
    assert not hypothesis_formation.has_hypothesis("No hypothesis yet.")


def test_hypothesis_extract_confidence():
    conf = hypothesis_formation.extract_confidence(_HYPOTHESIS_TEXT)
    assert conf == "Working"


def test_hypothesis_extract_text():
    text = hypothesis_formation.extract_hypothesis_text(_HYPOTHESIS_TEXT)
    assert text.startswith("Hypothesis:")
    assert "Confidence:" in text
    assert "Evidence for:" in text


# ---------------------------------------------------------------------------
# investigation_summary
# ---------------------------------------------------------------------------

_SUMMARY_DOC = """
# users_product_list/active investigation — 2026-04-28

**Question**: Why did product list drop on Android?

## Investigation
Queried pulse and release-agent. 1 metric investigated. Release correlation
not fully assessed due to unconfirmed repositories. 4 iterations used.

## Findings

### Metric findings
Metric: users_product_list/active
Window: 2026-04-14 to 2026-04-28
Coverage: complete

Findings:
- mx_android: 18% drop from 2026-04-22

Summary: Drop is Android-only.

### Release candidates
Not queried in this investigation.

## Hypothesis
Hypothesis: The android release caused the drop.
Confidence: Working

Evidence for:
- Temporal overlap.

Evidence against:
- None identified.

What would confirm this:
- Confirm repos.

What would refute this:
- No correlation found.

Next steps:
- Ask tech lead.

## Open questions
- Confirm android repo in release-agent.
"""


def test_summary_is_complete_true():
    assert investigation_summary.is_complete(_SUMMARY_DOC)


def test_summary_is_complete_false():
    assert not investigation_summary.is_complete("## Findings\nsome text")


def test_summary_extract_document_strips_preamble():
    text = "Here is your document:\n\n" + _SUMMARY_DOC
    doc = investigation_summary.extract_document(text)
    assert doc.startswith("# users_product_list")
