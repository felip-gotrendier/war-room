from __future__ import annotations

import json
from datetime import datetime, timezone

from war_room import orchestrator
from war_room.db import db_transaction
from war_room.models import ConversationContext


class ConversationNotFound(Exception):
    pass


class ConversationAccessDenied(Exception):
    pass


class ConversationRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def create(self, user_id: str, user_email: str) -> ConversationContext:
        ctx = orchestrator.create_conversation(user_id)
        # Known limitation (Phase 2b.1): title is fixed at creation time.
        # Auto-update to "<metric_name> investigation — YYYY-MM-DD" on first finding
        # is deferred to Phase 2b.2, together with the hypothesis-formation refactor
        # (ADR-010). Until then, if a user opens multiple conversations on the same
        # day, all titles will be identical in the sidebar.
        title = f"Investigation — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        with db_transaction(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations
                  (id, user_id, user_email, title, created_at, last_active_at,
                   iteration_count, conversation, current_hypothesis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.id,
                    ctx.user_id,
                    user_email,
                    title,
                    ctx.created_at,
                    ctx.last_active_at,
                    ctx.iteration_count,
                    json.dumps(ctx.messages),
                    ctx.current_hypothesis,
                ),
            )
        return ctx

    def load(self, id: str, user_id: str) -> ConversationContext:
        with db_transaction(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (id,)
            ).fetchone()
        # sqlite3.Row is fully materialized; safe to access after conn closes.
        if row is None:
            raise ConversationNotFound(id)
        if row["user_id"] != user_id:
            raise ConversationAccessDenied(id)
        return ConversationContext(
            id=row["id"],
            user_id=row["user_id"],
            messages=json.loads(row["conversation"]),
            iteration_count=row["iteration_count"],
            current_hypothesis=row["current_hypothesis"],
            created_at=row["created_at"],
            last_active_at=row["last_active_at"],
        )

    def save(self, ctx: ConversationContext, user_email: str) -> None:
        with db_transaction(self._db_path) as conn:
            conn.execute(
                """
                UPDATE conversations
                SET user_email         = ?,
                    last_active_at     = ?,
                    iteration_count    = ?,
                    conversation       = ?,
                    current_hypothesis = ?
                WHERE id = ?
                """,
                (
                    user_email,
                    ctx.last_active_at,
                    ctx.iteration_count,
                    json.dumps(ctx.messages),
                    ctx.current_hypothesis,
                    ctx.id,
                ),
            )

    def list_by_user(self, user_id: str) -> list[dict]:
        with db_transaction(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, last_active_at, iteration_count
                FROM conversations
                WHERE user_id = ?
                ORDER BY last_active_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, id: str, user_id: str) -> None:
        with db_transaction(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (id, user_id),
            )
            deleted = cursor.rowcount
        if deleted == 0:
            raise ConversationNotFound(id)
