from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator


def get_db_path() -> str:
    return os.environ.get("DB_PATH", "war-room.db")


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Both pragmas must be set on every connection (ADR-005, ADR-007).
    # foreign_keys is not persisted by SQLite; WAL is idempotent once set.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_transaction(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id                TEXT PRIMARY KEY,
  user_id           TEXT NOT NULL,
  user_email        TEXT NOT NULL,
  title             TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  last_active_at    TEXT NOT NULL,
  iteration_count   INTEGER NOT NULL DEFAULT 0,
  conversation      TEXT NOT NULL,
  current_hypothesis TEXT
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id
  ON conversations(user_id);

CREATE INDEX IF NOT EXISTS idx_conversations_user_last_active
  ON conversations(user_id, last_active_at DESC);

-- Publish / republish / delete routes for saved_investigations arrive in Phase 2b.2.
-- Table is created here so FK integrity with conversations is enforced from day one.
CREATE TABLE IF NOT EXISTS saved_investigations (
  id                 TEXT PRIMARY KEY,
  conversation_id    TEXT NOT NULL UNIQUE,
  published_by       TEXT NOT NULL,
  published_by_email TEXT NOT NULL,
  published_at       TEXT NOT NULL,
  title              TEXT NOT NULL,
  document           TEXT NOT NULL,
  original_question  TEXT NOT NULL,
  metrics_mentioned  TEXT NOT NULL,
  final_confidence   TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  user_email  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""


def init_schema(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        # executescript issues an implicit COMMIT before running, which is correct
        # for schema init at startup.
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Incremental migrations applied after CREATE TABLE IF NOT EXISTS."""
    # Phase 2b.2: original_question stores the first user message for publish metadata.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
    if "original_question" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN original_question TEXT")
