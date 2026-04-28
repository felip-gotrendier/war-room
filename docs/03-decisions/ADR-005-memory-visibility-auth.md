# ADR-005: Memory schema, visibility model, and authentication

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

ADR-001 established the high-level model: Google login, no domain restriction
at MVP, active investigations private to the investigating PM, published
investigations shared team-wide, any authenticated user can delete any
published investigation (team trust model). This ADR defines the concrete
implementation: the OAuth flow and library, the identity model, the data
schema for published investigations, the visibility implementation, the
storage backend, and the indexing strategy for retrieval.

The conversation model — each PM has multiple persistent conversations, each
corresponding to one investigation — is defined in ADR-007. This ADR records
the visibility contract that conversations imply and the schema for the
published investigations that make investigations team-visible.

---

## Decisions

### Authentication: Google OAuth 2.0 Authorization Code flow with PKCE,
### using authlib

**Decision**: use `authlib` (Python) implementing Authorization Code flow with
PKCE. Session established via an HTTP-only cookie containing an opaque session
ID; the session record and token data live server-side in SQLite (see storage
decision below).

Authorization Code with PKCE is the current best practice for web applications.
The implicit flow is deprecated in OAuth 2.1. Client credentials are for
machine-to-machine, not user-facing flows. PKCE eliminates the need for a
client secret in the token exchange, which is the recommended posture even for
confidential clients.

`authlib` is the most complete Python OAuth 2.0 library: supports all standard
flows, actively maintained, framework-agnostic. It does not assume a specific
web framework, which keeps the auth layer decoupled from the orchestrator's
serving layer.

The HTTP-only cookie + server-side session pattern means the access token and
user identity never reach JavaScript. This prevents XSS token theft without
requiring Content Security Policy enforcement at MVP.

No domain restriction is preserved from ADR-001.

Rejected alternative — `google-auth-oauthlib`: Google-specific, more limited
API surface, would lock the auth layer to Google even though the intent is
Google-as-provider-today with potential future flexibility.

Rejected alternative — client-side JWT stored in localStorage or in the cookie
directly: no server-side revocation capability. A session cannot be invalidated
without waiting for token expiry.

---

### Identity: Google `sub` claim as internal user ID

**Decision**: use the `sub` claim from Google's ID token as the internal
`user_id` in all war-room data. Store the user's email as a display-only
field, not as an identifier.

The `sub` claim is stable across email changes (e.g., company rebrand changes
the email domain; `sub` is unchanged). Using it as the primary key means user
data is stable under email changes without a migration. Email is stored for
display purposes and never used for joins or identity checks.

Rejected alternative — email as `user_id`: unstable under email changes,
PII in database primary keys.

Rejected alternative — war-room-generated UUID: adds a sub→UUID mapping table
that serves no purpose `sub` itself doesn't already serve at this scale.

---

### Storage backend: SQLite with WAL mode

**Decision**: single SQLite database file (`war-room.db`) for all war-room
persistent state. WAL (Write-Ahead Logging) mode enabled on every connection.

MVP scale is small team, low volume, single deployment. SQLite in WAL mode
handles concurrent reads without blocking and serializes writes; at MVP scale,
write serialization is not a bottleneck.

War-room maintains its own storage, independent of pulse (JSON files) and
release-agent (JSON files). Atlas Principle 5 — reuse only when it reduces
complexity — does not favor shared storage here. There is no GoTrendier-managed
Postgres instance available for war-room to use, and adding one introduces
infrastructure overhead without any MVP benefit.

The schema is portable to Postgres. If write volume or concurrency demands it,
the migration is a schema copy and data dump/restore, not an architectural
change.

Rejected alternative — Postgres: no existing instance to leverage; adds a
managed database service, connection pooling, and deployment coordination for
zero MVP benefit.

Rejected alternative — JSON files on disk: poor query capabilities for the
retrieval patterns required (by user, by metric, by date).

Rejected alternative — Redis: appropriate for ephemeral caching, not for
durable records. Conversations and published investigations must survive
server restarts.

---

### Conversations as the private-by-construction visibility layer

**Decision**: each war-room investigation is a `conversations` record owned
by the user who created it. Conversations are never exposed through any
team-facing API. No access control check beyond "is this conversation owned
by the authenticated user?" is needed — because no other user can request
another user's conversation by construction, not by permission check.

The `conversations` table schema is in ADR-007. This section records the
visibility contract: conversations = private by construction, no exception.

A conversation becomes team-visible only when the PM explicitly publishes it
(see published investigations below). Publishing does not change the
conversation's privacy — the conversation remains the PM's private artifact;
a separate `saved_investigations` record is created as the team-visible copy.

---

### Memory schema: published investigations

**Decision**: a published investigation is a row in the `saved_investigations`
table. Publishing is the explicit act of making an investigation's document
visible to the whole team. The primary artifact is a markdown string (produced
by the `investigation-summary` skill per ADR-006). Structured metadata fields
support indexing and retrieval.

Schema:

```sql
CREATE TABLE saved_investigations (
  id                 TEXT PRIMARY KEY,     -- UUID v4
  conversation_id    TEXT NOT NULL UNIQUE, -- FK to conversations.id (ADR-007)
  published_by       TEXT NOT NULL,        -- Google sub claim
  published_by_email TEXT NOT NULL,        -- display only
  published_at       TEXT NOT NULL,        -- ISO8601; updated on republish
  title              TEXT NOT NULL,
  document           TEXT NOT NULL,        -- full markdown document
  original_question  TEXT NOT NULL,        -- verbatim PM question
  metrics_mentioned  TEXT NOT NULL,        -- JSON array of metric name strings
  final_confidence   TEXT NOT NULL         -- "High", "Working", or "Speculative"
);
```

`UNIQUE` on `conversation_id` enforces the one-conversation-to-one-publication
constraint at the database layer.

`published_at` is updated on republish. The row is not replaced; document
content and `published_at` are updated in place. The team sees the updated
document in the same slot in the shared list.

`metrics_mentioned` is extracted by the orchestrator from the investigation
document before the publish transaction commits. Extraction is a text pass
over the document. If extraction fails, the transaction proceeds with
`metrics_mentioned = '[]'` — search is degraded but the publish is not blocked.

`final_confidence` is extracted from the final hypothesis-formation output
present in conversation context at publish time.

---

### Visibility model implementation

**Decision**: conversations are private by construction. Published
investigations are accessible to any authenticated user with no ACL.
Deletion is hard delete; unpublishing without deletion is not supported at MVP.

Conversations are not "hidden" through access control — they have no
team-facing API surface. The `conversations` table is an internal
implementation detail queried only through the owning user's identity.

Published investigations have no row-level security. The team trust model
from ADR-001 applies. Deletion is hard delete of the `saved_investigations`
row. The associated conversation is unaffected — it persists in the PM's
private conversation list.

Unpublishing without deletion is not supported at MVP. To remove a published
investigation from team view, the only mechanism is deletion. The underlying
conversation persists; the PM can republish from it at any time.

---

### Indexing and retrieval

**Decision**: three access patterns for published investigations:

1. **All published, most recent first**: default team view.
   `SELECT * FROM saved_investigations ORDER BY published_at DESC`

2. **By publishing user**: "published by me" filter.
   `WHERE published_by = :user_id ORDER BY published_at DESC`

3. **By metric**: investigations touching a specific metric.
   `WHERE metrics_mentioned LIKE '%"<metric_name>"%'`
   SQLite `json_each` is a cleaner alternative if LIKE produces false matches.

Full-text search via SQLite FTS5 on the `document` field is the Phase 2
upgrade if text-based metric matching proves insufficient.

---

## Consequences

**Positive**
- Auth layer uses the current industry standard (Authorization Code + PKCE).
- `sub`-based identity is stable under email changes.
- Zero-infrastructure storage at MVP.
- Visibility model is simple: conversations = private by construction,
  published investigations = shared by construction. No ACL logic.

**Negative / trade-offs**
- SQLite serializes writes. Under simultaneous publish operations (unlikely
  at MVP), writes queue. Migration to Postgres is the remedy if needed.
- `metrics_mentioned` extraction by text pass is imprecise. Abbreviated
  metric names may not be captured.
- Hard delete with no undo. No unpublish toggle at MVP.

**Constraints introduced**
- `war-room.db` must be on durable storage in the deployment environment.
  Ephemeral container storage will lose all state on restart.
- `PRAGMA foreign_keys = ON` must be set on every SQLite connection.
  SQLite does not enforce FK constraints by default.
- `metrics_mentioned` extraction must run before the publish commits.
  Failure must be non-blocking (degrade to empty array).
- `conversation_id UNIQUE` constraint must be present. The application should
  check before publishing to provide a meaningful error ("already published —
  use republish to update") rather than surfacing a constraint violation.

---

## Related decisions

- ADR-001 Section 4e — memory and visibility model established
- ADR-001 Section 4g — Google authentication and no-domain-restriction
- ADR-002 — iteration loop and conversation context
- ADR-006 — investigation document format (the `document` field content)
- ADR-007 — conversation persistence (the `conversations` table this schema
  references via FK)
