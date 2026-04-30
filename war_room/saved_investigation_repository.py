from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone

from war_room.db import db_transaction

_METRIC_RE = re.compile(r'\b[a-z][a-z0-9_]*/[a-z][a-z0-9_]*\b')


def extract_metrics_mentioned(document: str) -> list[str]:
    return sorted(set(_METRIC_RE.findall(document)))


class SavedInvestigationNotFound(Exception):
    pass


class SavedInvestigationRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def publish(
        self,
        conversation_id: str,
        published_by: str,
        published_by_email: str,
        title: str,
        document: str,
        original_question: str,
        final_confidence: str,
    ) -> dict:
        metrics = json.dumps(extract_metrics_mentioned(document))
        published_at = datetime.now(timezone.utc).isoformat()

        with db_transaction(self._db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM saved_investigations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()

        is_republish = existing is not None
        inv_id = existing["id"] if is_republish else secrets.token_hex(16)

        with db_transaction(self._db_path) as conn:
            if is_republish:
                conn.execute(
                    """
                    UPDATE saved_investigations
                    SET published_by = ?, published_by_email = ?, published_at = ?,
                        title = ?, document = ?, original_question = ?,
                        metrics_mentioned = ?, final_confidence = ?
                    WHERE conversation_id = ?
                    """,
                    (
                        published_by, published_by_email, published_at,
                        title, document, original_question,
                        metrics, final_confidence, conversation_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO saved_investigations
                      (id, conversation_id, published_by, published_by_email,
                       published_at, title, document, original_question,
                       metrics_mentioned, final_confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inv_id, conversation_id, published_by, published_by_email,
                        published_at, title, document, original_question,
                        metrics, final_confidence,
                    ),
                )

        return {
            "id": inv_id,
            "conversation_id": conversation_id,
            "published_at": published_at,
            "title": title,
            "document": document,
            "is_republish": is_republish,
        }

    def list_all(self) -> list[dict]:
        with db_transaction(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, published_by, published_by_email,
                       published_at, title, original_question, metrics_mentioned,
                       final_confidence
                FROM saved_investigations
                ORDER BY published_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, id: str) -> dict:
        with db_transaction(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM saved_investigations WHERE id = ?", (id,)
            ).fetchone()
        if row is None:
            raise SavedInvestigationNotFound(id)
        return dict(row)

    def get_by_conversation(self, conversation_id: str) -> dict | None:
        with db_transaction(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM saved_investigations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete(self, id: str) -> None:
        with db_transaction(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM saved_investigations WHERE id = ?", (id,)
            )
            deleted = cursor.rowcount
        if deleted == 0:
            raise SavedInvestigationNotFound(id)
