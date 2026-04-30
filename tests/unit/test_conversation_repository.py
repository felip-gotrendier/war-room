"""Unit tests for ConversationRepository.

All tests use a temporary file-based SQLite database so that FK enforcement
and WAL mode behave identically to production. `:memory:` would also work for
most tests, but FK CASCADE (which requires a connection opened with
PRAGMA foreign_keys=ON) must be verified against the real schema init path.
"""
from __future__ import annotations

import sqlite3

import pytest

from war_room.db import init_schema
from war_room.conversation_repository import (
    ConversationAccessDenied,
    ConversationNotFound,
    ConversationRepository,
)


@pytest.fixture
def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_schema(db_path)
    return ConversationRepository(db_path)


# ---------------------------------------------------------------------------
# create + load
# ---------------------------------------------------------------------------


def test_create_returns_conversation_context(repo):
    ctx = repo.create(user_id="sub-123", user_email="user@example.com")
    assert ctx.id
    assert ctx.user_id == "sub-123"
    assert ctx.iteration_count == 0
    assert ctx.messages == []
    assert ctx.current_hypothesis is None


def test_load_returns_persisted_context(repo):
    ctx = repo.create(user_id="sub-123", user_email="user@example.com")
    loaded = repo.load(ctx.id, "sub-123")
    assert loaded.id == ctx.id
    assert loaded.user_id == "sub-123"
    assert loaded.messages == []
    assert loaded.iteration_count == 0


def test_load_nonexistent_raises(repo):
    with pytest.raises(ConversationNotFound):
        repo.load("does-not-exist", "sub-123")


def test_load_wrong_user_raises(repo):
    ctx = repo.create(user_id="sub-123", user_email="user@example.com")
    with pytest.raises(ConversationAccessDenied):
        repo.load(ctx.id, "sub-other")


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_updates_messages_iteration_count_and_hypothesis(repo):
    ctx = repo.create(user_id="sub-123", user_email="user@example.com")
    ctx.messages.append({"role": "user", "content": "Hello"})
    ctx.current_hypothesis = "Hypothesis: something happened"
    ctx.iteration_count = 3
    repo.save(ctx, user_email="user@example.com")

    loaded = repo.load(ctx.id, "sub-123")
    assert loaded.messages == [{"role": "user", "content": "Hello"}]
    assert loaded.current_hypothesis == "Hypothesis: something happened"
    assert loaded.iteration_count == 3


def test_save_preserves_complex_messages(repo):
    ctx = repo.create(user_id="sub-789", user_email="c@example.com")
    ctx.messages = [
        {"role": "user", "content": [{"type": "text", "text": "Question"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Answer"}]},
    ]
    repo.save(ctx, user_email="c@example.com")

    loaded = repo.load(ctx.id, "sub-789")
    assert loaded.messages == ctx.messages


# ---------------------------------------------------------------------------
# persistence across repository instances
# ---------------------------------------------------------------------------


def test_persistence_survives_new_repository_instance(tmp_path):
    db_path = str(tmp_path / "persist.db")
    init_schema(db_path)

    repo1 = ConversationRepository(db_path)
    ctx = repo1.create(user_id="sub-456", user_email="other@example.com")
    ctx.messages.append({"role": "user", "content": "Persisted"})
    repo1.save(ctx, user_email="other@example.com")

    repo2 = ConversationRepository(db_path)
    loaded = repo2.load(ctx.id, "sub-456")
    assert loaded.messages == [{"role": "user", "content": "Persisted"}]


# ---------------------------------------------------------------------------
# list_by_user
# ---------------------------------------------------------------------------


def test_list_by_user_returns_only_own_conversations(repo):
    ctx_a1 = repo.create(user_id="sub-A", user_email="a@example.com")
    ctx_a2 = repo.create(user_id="sub-A", user_email="a@example.com")
    repo.create(user_id="sub-B", user_email="b@example.com")

    results = repo.list_by_user("sub-A")
    ids = {r["id"] for r in results}
    assert ids == {ctx_a1.id, ctx_a2.id}


def test_list_by_user_ordered_by_last_active_desc(repo):
    import time
    ctx1 = repo.create(user_id="sub-ord", user_email="o@example.com")
    time.sleep(0.01)  # ensure distinct last_active_at timestamps
    ctx2 = repo.create(user_id="sub-ord", user_email="o@example.com")

    results = repo.list_by_user("sub-ord")
    assert results[0]["id"] == ctx2.id
    assert results[1]["id"] == ctx1.id


def test_list_by_user_includes_expected_fields(repo):
    repo.create(user_id="sub-fields", user_email="f@example.com")
    results = repo.list_by_user("sub-fields")
    assert len(results) == 1
    row = results[0]
    assert {"id", "title", "created_at", "last_active_at", "iteration_count"} <= row.keys()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_conversation(repo):
    ctx = repo.create(user_id="sub-del", user_email="del@example.com")
    repo.delete(ctx.id, "sub-del")
    with pytest.raises(ConversationNotFound):
        repo.load(ctx.id, "sub-del")


def test_delete_nonexistent_raises(repo):
    with pytest.raises(ConversationNotFound):
        repo.delete("nonexistent-id", "sub-del")


def test_delete_wrong_user_raises(repo):
    ctx = repo.create(user_id="sub-owner", user_email="owner@example.com")
    with pytest.raises(ConversationNotFound):
        repo.delete(ctx.id, "sub-other")


# ---------------------------------------------------------------------------
# FK CASCADE: deleting a conversation removes its saved_investigation
# ---------------------------------------------------------------------------


def test_delete_cascades_to_saved_investigations(tmp_path):
    db_path = str(tmp_path / "cascade.db")
    init_schema(db_path)
    repo = ConversationRepository(db_path)
    ctx = repo.create(user_id="sub-cascade", user_email="c@example.com")

    # Insert a saved_investigation manually (publish routes arrive in Phase 2b.2)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        INSERT INTO saved_investigations
          (id, conversation_id, published_by, published_by_email,
           published_at, title, document, original_question,
           metrics_mentioned, final_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "si-cascade-1", ctx.id, "sub-cascade", "c@example.com",
            "2026-01-01T00:00:00+00:00", "Test Title", "Doc content",
            "Original question", "[]", "Working",
        ),
    )
    conn.commit()
    conn.close()

    repo.delete(ctx.id, "sub-cascade")

    conn2 = sqlite3.connect(db_path)
    conn2.execute("PRAGMA foreign_keys=ON")
    row = conn2.execute(
        "SELECT id FROM saved_investigations WHERE id = ?", ("si-cascade-1",)
    ).fetchone()
    conn2.close()
    assert row is None, "saved_investigation should have been deleted by CASCADE"
