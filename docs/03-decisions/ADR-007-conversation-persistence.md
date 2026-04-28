# ADR-007: Conversation persistence

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

War-room investigations are multi-step conversations bounded at 15 iterations
per investigation (ADR-002). A PM may investigate multiple incidents in
parallel, return to a conversation days or weeks after starting it, or want
to review the history of a past investigation without having published it.
This ADR defines the conversation model, the persistence schema, reconnect
behavior, and the lifecycle of conversations and their relationship to
published investigations.

The model is analogous to a persistent chat interface: each conversation is
a durable artifact owned by the user, accessible indefinitely, and never
purged automatically. Publishing (ADR-005) is the separate act of making a
conversation's document visible to the team — it does not affect the
conversation's existence or privacy.

---

## Decisions

### Multiple conversations per user; no automatic lifecycle

**Decision**: each PM can have any number of conversations open simultaneously.
There is no one-conversation-per-user constraint. All conversations persist
indefinitely until the PM explicitly deletes them. There is no automatic stale
detection, no automatic purge, no status lifecycle.

The primary motivation: a PM investigating a multi-platform incident may have
one conversation for the MX drop and another for the CO drop running in
parallel. A one-conversation constraint would force sequential investigation
where the use case demands concurrent.

Indefinite persistence eliminates a class of UX failures (returning to find
a conversation purged) without meaningful storage cost. At MVP scale — a small
team, investigations bounded at 15 iterations, conversation payload of
50–200 KB — accumulating conversations over months is not a storage concern.

Rejected alternative — one active conversation per user with stale/purge
lifecycle: imposes sequential investigation, creates surprise purges, adds
lifecycle complexity (background jobs, status transitions) that serves no
identified PM need.

---

### Conversation schema

**Decision**: the `conversations` table in `war-room.db`:

```sql
CREATE TABLE conversations (
  id                TEXT PRIMARY KEY,    -- UUID v4
  user_id           TEXT NOT NULL,       -- Google sub claim (ADR-005)
  user_email        TEXT NOT NULL,       -- display only
  title             TEXT NOT NULL,       -- auto-generated, editable by PM
  created_at        TEXT NOT NULL,       -- ISO8601
  last_active_at    TEXT NOT NULL,       -- ISO8601; updated on every orchestrator call
  iteration_count   INTEGER NOT NULL DEFAULT 0,
  conversation      TEXT NOT NULL,       -- JSON array: full LLM message history + tool results
  current_hypothesis TEXT               -- latest hypothesis-formation output, or NULL
);
```

`last_active_at` is updated on every orchestrator call. Its only purpose is
ordering the conversation list in the PM's sidebar (most recent first). It
does not trigger any lifecycle transition.

`iteration_count` tracks iterations used in this conversation. The 15-iteration
cap from ADR-002 applies per conversation: when the cap is reached, the
orchestrator produces the forced summary and no further queries are accepted
in that conversation. The conversation remains readable and publishable; the
PM opens a new conversation to continue the investigation.

`conversation` is the full LLM message history serialized as JSON — the same
array the orchestrator maintains in memory during an active investigation.
At ADR-002's 15-iteration cap with typical tool results of a few KB each,
this field is expected to be 50–200 KB per conversation. The iteration cap
bounds the maximum size.

`current_hypothesis` caches the latest `hypothesis-formation` output for
restoring the hypothesis display in the UI without re-parsing the full
conversation. NULL before any hypothesis has been formed.

---

### Reconnect: load conversation by ID

**Decision**: when a PM returns to war-room and selects a conversation, the
orchestrator loads the record by ID, deserializes `conversation` into context,
and presents the full history in the UI. There is no stale check, no status
gate, no expiry. A conversation opened today or six months ago loads
identically.

If `iteration_count` has reached the cap (15): the conversation is presented
as read-only. The PM can view the history, publish from the existing hypothesis,
or open a new conversation.

If `iteration_count` is below the cap: the PM can continue querying immediately.

---

### Conversation title

**Decision**: at creation, the title is auto-generated as
`Investigation — <YYYY-MM-DD>`. When the first funnel-investigation finding
is produced, the orchestrator updates the title to
`<metric_name> investigation — <YYYY-MM-DD>`. The PM can edit the title at
any time from the conversation UI.

Title auto-update on first finding makes the PM's sidebar self-describing
without requiring manual naming.

---

### Backend: SQLite, same database as ADR-005

**Decision**: the `conversations` table lives in `war-room.db` alongside
`saved_investigations`.

`saved_investigations.conversation_id` is a FK into `conversations.id`.
Having both tables in the same database enforces FK integrity and enables
CASCADE semantics at the DB layer. Single connection pool, single backup
target, single `PRAGMA` configuration surface.

Rejected alternative — separate conversations database: no benefit at this
scale; FK integrity cannot span SQLite database files.

Rejected alternative — in-memory only: conversations do not survive server
restarts. Unacceptable for the reconnect use case.

---

### Relationship to published investigations

**Decision**: the FK is on `saved_investigations.conversation_id` (ADR-005
schema). A conversation may have zero or one published investigation at any
time, enforced by the `UNIQUE` constraint on `conversation_id` in
`saved_investigations`.

A conversation is unaffected by whether it has been published. Publishing
creates a row in `saved_investigations`; unpublishing (deletion) removes
that row. The conversation persists in both cases.

**First publish** (no prior publication):
```sql
INSERT INTO saved_investigations (id, conversation_id, ...) VALUES (?, ?, ...)
```

**Republish** (update existing publication after further investigation):
```sql
UPDATE saved_investigations
SET document = ?, published_at = ?, title = ?, final_confidence = ?
WHERE conversation_id = ?
```
The team sees the updated document in the same slot. The published document
is a snapshot frozen at publish or republish time; it does not auto-update
as the PM continues the conversation.

**Unpublish** (remove from team view without deleting the conversation):
```sql
DELETE FROM saved_investigations WHERE conversation_id = ?
```
The conversation persists. The PM can republish from it later.

Rejected alternative — FK in the other direction (`conversations.
published_investigation_id`): insert flow requires a two-step write (INSERT
saved_investigations → UPDATE conversations). No advantage over the current
direction that justifies the added complexity.

---

### Deletion

**Decision**: conversations are deleted by explicit PM action (UI-driven,
one at a time). Deletion is hard delete of the `conversations` row. If the
conversation has a published investigation, that row is also deleted (CASCADE
enforced by FK with `ON DELETE CASCADE` on `saved_investigations.conversation_id`).

No bulk delete at MVP. No automatic purge.

The CASCADE ensures deleting a conversation cannot leave an orphaned
`saved_investigations` row. The UI must present a confirmation step when the
conversation has a published investigation: "This will also remove the
published investigation from the team view."

Rejected alternative — prevent deletion of conversations with published
investigations: forces the PM to unpublish before cleaning up, adding an
unnecessary step.

Rejected alternative — soft delete: adds filtered queries everywhere. No
recovery use case identified at MVP.

---

## Consequences

**Positive**
- PMs can run parallel investigations without constraint.
- No surprise purges. A conversation started last month is still there.
- No lifecycle jobs. No background processes to operate or monitor.
- Reconnect is trivial: load by ID, no gate, no state machine.

**Negative / trade-offs**
- Conversations accumulate indefinitely for users who never clean up. This
  is the expected behavior. At MVP scale it is not a storage concern; a manual
  archive UI is the appropriate future remedy if needed — not automatic purge.
- Cascade delete is consequential. Deleting a conversation removes the
  published investigation from team view. The UI confirmation step is the
  only safeguard; there is no undo.
- The 15-iteration cap per conversation means a PM who has exhausted a
  conversation must open a new one to continue investigating. Establishing
  context in the new conversation is manual. A "continuation conversation"
  that inherits key findings from a parent is a potential Phase 2 refinement
  if this proves to be a friction point in practice.

**Constraints introduced**
- `PRAGMA foreign_keys = ON` must be set on every SQLite connection.
  The CASCADE on `saved_investigations` requires FK enforcement to be active.
  SQLite does not enable this by default.
- `ON DELETE CASCADE` must be specified on the `saved_investigations.
  conversation_id` FK definition. The purge check from the previous design
  is replaced by this DB-layer constraint.
- The orchestrator must update `last_active_at` and `iteration_count` on
  every orchestrator call, before returning the turn's response.
- The 15-iteration cap check must occur before accepting a new PM query.
  Once `iteration_count = 15`, the conversation is read-only for new queries.
  The orchestrator must surface this state clearly in the UI.

---

## Related decisions

- ADR-001 Section 4e — memory and visibility model established
- ADR-002 — 15-iteration cap per investigation
- ADR-005 — `saved_investigations` table and FK; storage backend (SQLite)
- ADR-006 — investigation document produced when publishing
