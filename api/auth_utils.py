from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from war_room.db import db_transaction

COOKIE_NAME = "war_room_session"
SESSION_MAX_AGE_DAYS = 30


@dataclass
class AuthUser:
    user_id: str    # Google sub claim (ADR-005)
    user_email: str  # display only — never used for identity checks


def create_session(db_path: str, user_id: str, user_email: str) -> str:
    session_id = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_MAX_AGE_DAYS)
    with db_transaction(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, user_email, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_id,
                user_email,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
    return session_id


def get_session_user(db_path: str, session_id: str) -> AuthUser | None:
    with db_transaction(db_path) as conn:
        row = conn.execute(
            "SELECT user_id, user_email, expires_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None  # expired; stale row stays until next cleanup
    return AuthUser(user_id=row["user_id"], user_email=row["user_email"])


def delete_session(db_path: str, session_id: str) -> None:
    with db_transaction(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
