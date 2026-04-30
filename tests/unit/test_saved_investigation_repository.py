"""Unit tests for SavedInvestigationRepository and extract_metrics_mentioned.

All tests use a temporary file-based SQLite database (tmp_path) so that FK
enforcement and CASCADE behaviour match production.
"""
from __future__ import annotations

import pytest

from war_room.db import init_schema
from war_room.conversation_repository import ConversationRepository
from war_room.saved_investigation_repository import (
    SavedInvestigationNotFound,
    SavedInvestigationRepository,
    extract_metrics_mentioned,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test.db")
    init_schema(path)
    return path


@pytest.fixture
def repos(db_path):
    return ConversationRepository(db_path), SavedInvestigationRepository(db_path)


def _make_conversation(conv_repo: ConversationRepository) -> str:
    ctx = conv_repo.create(user_id="sub-1", user_email="user@example.com")
    return ctx.id


# ---------------------------------------------------------------------------
# extract_metrics_mentioned
# ---------------------------------------------------------------------------


def test_extract_metrics_finds_slash_names():
    doc = "The metric orders/count increased while checkout/errors stayed flat."
    result = extract_metrics_mentioned(doc)
    assert "orders/count" in result
    assert "checkout/errors" in result


def test_extract_metrics_deduplicates():
    doc = "orders/count orders/count"
    assert extract_metrics_mentioned(doc) == ["orders/count"]


def test_extract_metrics_returns_sorted():
    doc = "z/metric a/metric m/metric"
    assert extract_metrics_mentioned(doc) == ["a/metric", "m/metric", "z/metric"]


def test_extract_metrics_ignores_uppercase():
    doc = "Orders/Count is uppercase so should not match"
    assert extract_metrics_mentioned(doc) == []


def test_extract_metrics_empty_document():
    assert extract_metrics_mentioned("") == []


# ---------------------------------------------------------------------------
# publish (new)
# ---------------------------------------------------------------------------


def test_publish_returns_dict_with_expected_keys(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)

    result = inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="My Investigation",
        document="orders/count dropped by 20%.",
        original_question="Why did orders drop?",
        final_confidence="Likely a deployment issue.",
    )

    assert result["id"]
    assert result["conversation_id"] == conv_id
    assert result["title"] == "My Investigation"
    assert result["document"] == "orders/count dropped by 20%."
    assert result["published_at"]
    assert result["is_republish"] is False


def test_publish_stores_metrics_mentioned(db_path, repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)

    inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="T",
        document="orders/count and checkout/errors look suspicious.",
        original_question="Q",
        final_confidence="C",
    )

    inv = inv_repo.get_by_conversation(conv_id)
    import json
    metrics = json.loads(inv["metrics_mentioned"])
    assert "orders/count" in metrics
    assert "checkout/errors" in metrics


# ---------------------------------------------------------------------------
# publish (republish / idempotent)
# ---------------------------------------------------------------------------


def test_republish_updates_existing_row(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)

    first = inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="Original Title",
        document="v1 document.",
        original_question="Q",
        final_confidence="C",
    )

    second = inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="Updated Title",
        document="v2 document.",
        original_question="Q",
        final_confidence="C2",
    )

    assert second["id"] == first["id"]
    assert second["is_republish"] is True
    assert second["title"] == "Updated Title"
    assert second["document"] == "v2 document."


def test_republish_does_not_create_duplicate(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)

    for _ in range(3):
        inv_repo.publish(
            conversation_id=conv_id,
            published_by="sub-1",
            published_by_email="user@example.com",
            title="T",
            document="doc",
            original_question="Q",
            final_confidence="C",
        )

    assert len(inv_repo.list_all()) == 1


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_returns_record(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)
    result = inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="T",
        document="doc",
        original_question="Q",
        final_confidence="C",
    )

    inv = inv_repo.get(result["id"])
    assert inv["id"] == result["id"]
    assert inv["title"] == "T"


def test_get_nonexistent_raises(repos):
    _, inv_repo = repos
    with pytest.raises(SavedInvestigationNotFound):
        inv_repo.get("does-not-exist")


# ---------------------------------------------------------------------------
# get_by_conversation
# ---------------------------------------------------------------------------


def test_get_by_conversation_returns_none_when_not_published(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)
    assert inv_repo.get_by_conversation(conv_id) is None


def test_get_by_conversation_returns_record_after_publish(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)
    inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="T",
        document="doc",
        original_question="Q",
        final_confidence="C",
    )
    inv = inv_repo.get_by_conversation(conv_id)
    assert inv is not None
    assert inv["conversation_id"] == conv_id


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


def test_list_all_returns_all_investigations(repos):
    conv_repo, inv_repo = repos
    ids = [_make_conversation(conv_repo) for _ in range(3)]
    for conv_id in ids:
        inv_repo.publish(
            conversation_id=conv_id,
            published_by="sub-1",
            published_by_email="user@example.com",
            title="T",
            document="doc",
            original_question="Q",
            final_confidence="C",
        )

    results = inv_repo.list_all()
    assert len(results) == 3


def test_list_all_ordered_by_published_at_desc(repos):
    import time
    conv_repo, inv_repo = repos

    conv_id_1 = _make_conversation(conv_repo)
    inv_repo.publish(
        conversation_id=conv_id_1,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="First",
        document="doc",
        original_question="Q",
        final_confidence="C",
    )
    time.sleep(0.01)
    conv_id_2 = _make_conversation(conv_repo)
    inv_repo.publish(
        conversation_id=conv_id_2,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="Second",
        document="doc",
        original_question="Q",
        final_confidence="C",
    )

    results = inv_repo.list_all()
    assert results[0]["title"] == "Second"
    assert results[1]["title"] == "First"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_investigation(repos):
    conv_repo, inv_repo = repos
    conv_id = _make_conversation(conv_repo)
    result = inv_repo.publish(
        conversation_id=conv_id,
        published_by="sub-1",
        published_by_email="user@example.com",
        title="T",
        document="doc",
        original_question="Q",
        final_confidence="C",
    )

    inv_repo.delete(result["id"])
    with pytest.raises(SavedInvestigationNotFound):
        inv_repo.get(result["id"])


def test_delete_nonexistent_raises(repos):
    _, inv_repo = repos
    with pytest.raises(SavedInvestigationNotFound):
        inv_repo.delete("does-not-exist")
