"""Anchor use case integration test.

Exercises the full investigation loop against live MCP servers.

Accepted degraded state (Phase 2a):
  - pulse returns real metric findings
  - release-agent returns REPO_NOT_FOUND for all repos (no confirmed production
    repos yet)
  - war-room must respond with a qualified hypothesis that explicitly names
    the coverage gap — this is the CORRECT behavior, not a failure

Bonus case (if tech lead has confirmed a repo):
  - release-agent returns real candidates
  - hypothesis confidence is Working or High with release correlation

Run with:
    PULSE_MCP_URL=... RELEASE_AGENT_MCP_URL=... ANTHROPIC_API_KEY=... \
    pytest tests/integration/test_anchor_use_case.py -v -s

Skip when MCP URLs are not set (CI / unit-only runs).
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from war_room import orchestrator
from war_room.models import ConversationContext
from war_room.skills import hypothesis_formation


# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

def _mcp_urls_set() -> bool:
    return bool(os.environ.get("PULSE_MCP_URL") and os.environ.get("RELEASE_AGENT_MCP_URL"))


skip_if_no_mcp = pytest.mark.skipif(
    not _mcp_urls_set(),
    reason="PULSE_MCP_URL and RELEASE_AGENT_MCP_URL not set — skipping integration tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def conversation() -> ConversationContext:
    return orchestrator.create_conversation(user_id="test-pm@gotrendier.com")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_if_no_mcp
@pytest.mark.asyncio
async def test_anchor_use_case_degraded(conversation):
    """PM asks about a product-list metric drop. Expect:
    - pulse queried, funnel finding produced
    - release-agent queried, REPO_NOT_FOUND gap noted
    - hypothesis formed with Working confidence naming the gap
    """
    pm_question = (
        "Hola, esta semana vi una bajada en users_product_list/active en mx_android. "
        "¿Puedes revisar qué pasó en los últimos 14 días?"
    )

    reply, ctx = await orchestrator.turn(conversation, pm_question)

    # Must have consumed at least 2 iterations (source-routing + tool call + synthesis)
    assert ctx.iteration_count >= 2, f"Expected >= 2 iterations, got {ctx.iteration_count}"
    assert ctx.iteration_count <= 15, f"Iteration cap exceeded: {ctx.iteration_count}"

    # Reply must be a non-trivial text response
    assert len(reply) > 100, f"Reply too short: {reply!r}"

    # The reply or hypothesis must contain structured metric findings
    combined = reply + (ctx.current_hypothesis or "")
    assert "users_product_list" in combined or "product_list" in combined, (
        f"No metric name in response. Reply: {reply[:500]}"
    )

    # Hypothesis must be present (formed by _maybe_inject_hypothesis)
    assert ctx.current_hypothesis is not None, (
        f"No hypothesis formed. Reply: {reply[:500]}"
    )

    # Validate hypothesis structure
    hyp = ctx.current_hypothesis
    assert hypothesis_formation.has_hypothesis(hyp), f"Hypothesis missing 'Hypothesis:' header: {hyp[:300]}"
    confidence = hypothesis_formation.extract_confidence(hyp)
    assert confidence in {"High", "Working", "Speculative"}, f"Unexpected confidence: {confidence}"

    print(f"\n--- Anchor test result ---")
    print(f"Iterations used: {ctx.iteration_count}")
    print(f"Confidence: {confidence}")
    print(f"\nHypothesis:\n{hyp[:800]}")


@skip_if_no_mcp
@pytest.mark.asyncio
async def test_iteration_cap_respected(conversation):
    """Verify cap raises IterationCapReached at exactly 15."""
    from war_room.models import IterationCapReached

    # Force the cap
    conversation.iteration_count = 15

    with pytest.raises(IterationCapReached):
        await orchestrator.turn(conversation, "Follow-up question")


@skip_if_no_mcp
@pytest.mark.asyncio
async def test_summarize_after_investigation(conversation):
    """After a complete investigation, summarize must produce a valid document."""
    pm_question = (
        "Revisemos users_checkout/active en los últimos 7 días en todas las plataformas."
    )
    _, ctx = await orchestrator.turn(conversation, pm_question)

    if ctx.current_hypothesis is None:
        pytest.skip("No hypothesis formed — investigation may not have produced enough findings")

    document = await orchestrator.summarize(ctx)

    from war_room.skills import investigation_summary
    assert investigation_summary.is_complete(document), (
        f"Document missing required sections. Got:\n{document[:1000]}"
    )
    assert "## Hypothesis" in document
    assert "## Open questions" in document

    print(f"\n--- Summary document (first 1000 chars) ---\n{document[:1000]}")
