"""Unit tests for auth_utils session management.

These tests exercise create_session / get_session_user / delete_session
against a real (tmp_path) SQLite database.  No Google OAuth credentials
or network access are required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.auth_utils import (
    AuthUser,
    SESSION_MAX_AGE_DAYS,
    create_session,
    delete_session,
    get_session_user,
)
from war_room.db import db_transaction, init_schema


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "auth_test.db")
    init_schema(path)
    return path


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


def test_create_session_returns_hex_token(db_path):
    sid = create_session(db_path, "sub-123", "user@example.com")
    assert len(sid) == 64  # secrets.token_hex(32) → 64 hex chars
    assert all(c in "0123456789abcdef" for c in sid)


def test_create_session_persists_row(db_path):
    sid = create_session(db_path, "sub-123", "user@example.com")
    with db_transaction(db_path) as conn:
        row = conn.execute(
            "SELECT user_id, user_email FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
    assert row["user_id"] == "sub-123"
    assert row["user_email"] == "user@example.com"


def test_create_session_sets_30_day_expiry(db_path):
    before = datetime.now(timezone.utc)
    sid = create_session(db_path, "sub-123", "user@example.com")
    after = datetime.now(timezone.utc)

    with db_transaction(db_path) as conn:
        row = conn.execute(
            "SELECT expires_at FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
    expires = datetime.fromisoformat(row["expires_at"])
    expected_min = before + timedelta(days=SESSION_MAX_AGE_DAYS)
    expected_max = after + timedelta(days=SESSION_MAX_AGE_DAYS)
    assert expected_min <= expires <= expected_max


# ---------------------------------------------------------------------------
# get_session_user
# ---------------------------------------------------------------------------


def test_get_session_user_returns_auth_user(db_path):
    sid = create_session(db_path, "sub-abc", "abc@example.com")
    user = get_session_user(db_path, sid)
    assert isinstance(user, AuthUser)
    assert user.user_id == "sub-abc"
    assert user.user_email == "abc@example.com"


def test_get_session_user_nonexistent_returns_none(db_path):
    assert get_session_user(db_path, "does-not-exist") is None


def test_get_session_user_expired_returns_none(db_path):
    sid = create_session(db_path, "sub-exp", "exp@example.com")
    # Manually backdate expires_at to the past
    with db_transaction(db_path) as conn:
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", sid),
        )
    assert get_session_user(db_path, sid) is None


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def test_delete_session_removes_row(db_path):
    sid = create_session(db_path, "sub-del", "del@example.com")
    delete_session(db_path, sid)
    assert get_session_user(db_path, sid) is None


def test_delete_session_nonexistent_is_silent(db_path):
    # Should not raise
    delete_session(db_path, "nonexistent-session-id")


# ---------------------------------------------------------------------------
# isolation: sessions from different users do not interfere
# ---------------------------------------------------------------------------


def test_sessions_isolated_by_user(db_path):
    sid_a = create_session(db_path, "sub-A", "a@example.com")
    sid_b = create_session(db_path, "sub-B", "b@example.com")

    user_a = get_session_user(db_path, sid_a)
    user_b = get_session_user(db_path, sid_b)

    assert user_a.user_id == "sub-A"
    assert user_b.user_id == "sub-B"

    delete_session(db_path, sid_a)
    assert get_session_user(db_path, sid_a) is None
    assert get_session_user(db_path, sid_b) is not None
