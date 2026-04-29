from __future__ import annotations

from war_room.models import (
    ConversationContext,
    Coverage,
    IterationCapReached,
    WarRoomFinding,
)


def test_coverage_fields():
    c = Coverage(
        requested='{"metric_name": "users_checkout/active"}',
        covered="",
        is_complete=False,
        gaps=["gap 1"],
        freshness_at=None,
    )
    assert c.is_complete is False
    assert c.gaps == ["gap 1"]
    assert c.freshness_at is None


def test_war_room_finding():
    f = WarRoomFinding(
        source="pulse",
        tool="check_metric",
        data={"anomalies": []},
        coverage=Coverage(
            requested="{}",
            covered="{}",
            is_complete=True,
            gaps=[],
            freshness_at="2026-04-27T08:00:00Z",
        ),
    )
    assert f.source == "pulse"
    assert f.coverage.is_complete is True


def test_conversation_context_defaults():
    ctx = ConversationContext(id="abc", user_id="user1", messages=[])
    assert ctx.iteration_count == 0
    assert ctx.current_hypothesis is None
    assert ctx.created_at is not None
    assert ctx.last_active_at is not None


def test_iteration_cap_is_exception():
    try:
        raise IterationCapReached
    except IterationCapReached:
        pass
    else:
        raise AssertionError("IterationCapReached not raised")
