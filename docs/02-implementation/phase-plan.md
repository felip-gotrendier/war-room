# War-room — construction phase plan

This document tracks the phases of war-room's construction from initial documentation to production deployment. It is complementary to ADR-001 (which defines what war-room is) and describes when each piece is built, what must be true before the next phase begins, and where coordination with other Atlas sessions is required.

---

## Phase 0 — Project foundation *(current)*

**Scope**

- ADR-001: vision, scope, and core architectural decisions
- Context document (equivalent of `release-agent/docs/context.md`)
- `AGENTS.md`: onboarding instructions for future Claude sessions in this repository
- Directory scaffold: documented structure; not populated with production code

**Produces code?** No.

**Blocked by** Nothing.

**Definition of done**
- ADR-001 accepted and committed
- A Claude session starting fresh from `AGENTS.md` and the context document can understand what war-room is, what decisions have been made, and what Phase 1a requires

**External coordination** None.

---

## Phase 1a — Critical design for external coordination

**Scope**

Everything that produces input for the `pulse` and `release-agent` sessions. These go first to unblock their work as early as possible.

- **ADR: iteration loop design** — termination conditions, max steps, error handling within the loop. Required before the MCP contract can be fully specified, since the contract must fit the loop's needs.
- **ADR: MCP contract for war-room sources** — complete tool signatures for `pulse` and `release-agent`, coverage metadata format, error codes. This is the formal specification that both upstream sessions receive as implementation input.
- **Specification: pulse MCP server** — contract for `get_recent_anomalies()`, `check_metric()`, `trigger_scan()`, and the coverage metadata schema. Delivered to the `pulse` session.
- **Specification: release-agent on-demand mode** — contract for `get_releases()`, `get_release()`, `explain_release()`. Input for the `release-agent` ADR.
- **Skill specifications** — each initial skill defined as a markdown document (what it does, what sources it consults, what it returns, what it requires from the knowledge base). Required before finalizing the MCP contract, since skills drive what tools war-room actually needs.
- **Knowledge base skeleton** — directory structure and stub files for source definitions, investigation playbooks, GoTrendier metric context. Required before finalizing coverage metadata requirements.
- **ADR: prompting strategy for source routing** — how the LLM selects and sequences sources given a PM question.

**Produces code?** No. One exception: knowledge base validation scripts — strict parsers that verify knowledge base files conform to their schema. Consistent with the principle of failing fast on internal contracts.

**Blocked by** Nothing external. War-room owns all of this.

**Definition of done**
- Iteration loop ADR, MCP contract ADR, and source routing ADR accepted
- Pulse and release-agent specifications written, reviewed by their respective Claude sessions, and confirmed as actionable implementation inputs
- All initial skill specifications committed
- Knowledge base skeleton committed

**External coordination**
- `pulse` session: review the pulse MCP server specification. Confirm `trigger_scan` and the coverage metadata format are implementable as specified. Flag any constraint that would require revising the war-room contract.
- `release-agent` session: same review for the on-demand mode specification.

---

## Phase 1b — Internal design

**Scope**

Design decisions war-room can make independently, while upstream sessions implement their Phase 1a outputs. Running Phase 1b in parallel with upstream implementation compresses the calendar.

- **ADR: memory schema, visibility model, and authentication** — a single ADR covering three tightly coupled decisions. The rationale for bundling: identity (Google login), session ownership (active sessions belong to the authenticated user), and shared visibility (saved investigations are visible to all authenticated users) form one coherent contract. Separating them into three ADRs would fragment a system that can be expressed cleanly as one. The ADR covers: Google OAuth implementation, structured artifact schema for saved investigations, storage backend, retrieval indexing, and the team-trust deletion policy.
- **ADR: investigation document format** — sections, generation logic, format (analogous to `pulse`'s scan-report-format ADR)
- **ADR: session persistence** — database or in-memory store, session lifecycle, reconnection behavior

**Produces code?** No.

**Blocked by** Nothing external. Can run in parallel with upstream Phase 1a implementation.

**Definition of done**
- All three ADRs accepted
- A developer can begin Phase 2 without unresolved design questions blocking any component

**Note**: if the interval between Phase 1a delivery and Phase 2 start extends beyond Phase 1b, this window is also used for the frontend tech stack decision (implementation ADR) and refining the knowledge base content.

---

## Phase 2 — Core backend

**Scope**

First production code. War-room must be able to conduct a complete investigation from a Python script.

- Orchestrator: reads knowledge base, invokes skills, assembles responses
- MCP client infrastructure: connects to `pulse` and `release-agent`
- Skills: at minimum `funnel-investigation` and `release-metric-correlation` (the two required for the anchor use case)
- Knowledge base populated: source definitions, GoTrendier metric context (funnel stages, platform benchmarks, known seasonality), initial investigation playbooks
- Iteration loop with termination conditions from Phase 1a
- Memory backend: save and retrieve investigations across script runs

**Produces code?** Yes — first production code.

**Blocked by**
- Phases 1a and 1b complete
- `pulse` functional with a stable MCP server exposing `get_recent_anomalies()`, `check_metric()`, `trigger_scan()`, and coverage metadata as specified in the Phase 1a contract
- `release-agent` on-demand mode available via MCP as specified

"Pulse functional" means: pulse is running, its daily scans produce data, and its MCP server is stable. No external user validation requirement beyond Felip. (Rationale: ADR-001, Hard MVP dependencies.)

**Definition of done**
- A Python script demonstrates all five MVP capabilities against real data
- The anchor use case produces a coherent, evidence-backed response
- Cases A and C honesty behavior is observable in the script output
- At least one investigation can be saved and retrieved in a second independent script run

---

## Phase 3 — HTTP layer and web UI

**Scope**

Everything that makes war-room accessible to a PM without writing Python.

- FastAPI backend: session management, token streaming, memory API
- Web chat frontend: functional UI for Felip's use — not polished for a wider team, but usable end-to-end
- Session persistence: conversation survives browser disconnect-reconnect
- Streaming: tokens appear progressively during long tool-call chains, not as a single block at the end

**Produces code?** Yes.

**Blocked by** Phase 2 complete.

**Definition of done**
- Felip can open a browser, ask the anchor use case question, and receive a complete investigation response
- The conversation persists if the browser is closed and reopened
- Tokens stream visibly during the investigation

---

## Phase 4 — Production deployment and real use

**Scope**

The difference between Phase 2 and Phase 4 is not "Felip vs external users" — it is "Python script with real data" versus "web application with real data accessible without running locally."

- Google login implementation with shared visibility for saved investigations, per Phase 1b ADR
- Deployment: application accessible via browser without a local development environment
- Knowledge base calibration: adjust playbooks and prompts based on observed behavior in real investigation runs
- Prompt refinement: based on observed honesty failures, hypothesis quality, and redirection handling in production

**Produces code?** Yes — auth, deployment configuration, and knowledge base edits.

**Blocked by** Phase 3 complete.

**Definition of done**
- Felip can open war-room in a browser, authenticate with Google, and use it to investigate real GoTrendier incidents
- The five MVP capabilities demonstrated against production data, not test fixtures
- The anchor use case produces output Felip would actually act on

MVP validation does not end at Phase 4. It becomes a continuous process of real use. Phase 4's completion criterion is deployment and first real investigation — not a formal review gate.

---

## Deferred decisions and tech debt

### Phase 2c — Tool invocation permission policy

**Observed behaviour (Phase 2b.2, 2026-04-30):** war-room prompts the user
for confirmation before invoking tools with side effects (e.g. `trigger_scan`).
For the intended use case — a PM conducting an investigation — this is
redundant friction: the PM who opens war-room and asks a question has
implicitly authorised all reads and low-cost writes needed to answer it.

**Deferred to Phase 2c.** Requires:
1. A new ADR articulating a three-tier invocation policy:
   - *Read tools* (`check_metric`, `get_recent_anomalies`, `get_releases`,
     `get_release`, `explain_release`) — invoke automatically, no prompt.
   - *Cost tools* (`trigger_scan`, future batch operations) — invoke
     automatically but report cost/latency in the progress indicator.
   - *Destructive tools* (none currently; any future tool with irreversible
     external effects) — require explicit confirmation.
2. Tool metadata field in the MCP contract (e.g. `invocation_policy: auto |
   cost | destructive`) consumed by the orchestrator.
3. Orchestrator modification to read the policy field and bypass the default
   Claude-driven confirmation for `auto` and `cost` tools.

**Workaround:** respond "sí" to the confirmation prompt. Does not degrade
investigation quality.

### Phase 2c — tool_start event: review inputs for sensitive data

**Observed (Phase 2b.2 C4, 2026-04-30):** the `tool_start` SSE event now includes
`"input": block.input` so the frontend can display metadata (metric name, repo, etc.)
in the tool card before the result arrives. Current pulse and release-agent inputs are
innocus (metric names, day counts, repo identifiers).

**Deferred review before rita or any future tool integration.** When a new tool is
wired up, verify that its input dict does not contain secrets (API keys, session tokens,
PII, or internal identifiers that should not travel to the browser). If a tool input
contains sensitive fields, strip them in `_compact_ui_data` or add an explicit
`_safe_input(tool_name, input)` filter before the `tool_start` event is emitted.

---

### Phase 2c — Skill prompt display filtering

**Observed behaviour (Phase 2b.2, 2026-04-30):** `ctx.messages` contains raw skill
prompt messages (`role: user`, content starting with `"You are "`) and intermediate
assistant messages (e.g. source-routing planning text). Both must be hidden from the
conversation view.

**Current implementation:** `_display_messages()` in `api/ui_routes.py` groups
messages into PM-turn blocks by extracting the PM question from each skill prompt
(last `\n\n`-delimited section). Within each block, it shows: (1) the PM question
once; (2) the last assistant text message (the final reply). All intermediate assistant
messages and tool_result user messages are hidden. **Fragility:** assumes skill prompts
start with `"You are "` and embed the PM question as the last section. If either
convention changes, the filter silently breaks.

**Deferred to Phase 2c.** Robust fix: tag messages at creation time in the orchestrator,
e.g. `{"role": "user", "content": ..., "_skill_prompt": True}`, and strip tagged
messages in the display layer without text-matching. Requires a coordinated change to
`orchestrator.py` and `ui_routes.py`.

---

## Phase 2b.2 — C5: header polish and source status indicators

**Status**: closed 2026-04-30. Backend (ping + `/sources/status`), frontend (status dots + chart re-render), tests (3 unit tests for the endpoint), and empirical verification on Felip's Mac all complete.

### α — Chart re-render on dark/light theme toggle

**File**: `api/static/stream.js`

Chart.js instances read `isDark` at creation time and are not updated when
the user toggles the theme via the Alpine.js button in the header. Charts
created in dark mode retain dark grid/tick colors in light mode and vice versa.

**Fix**: extract chart creation into `_createChart(canvas, platforms)`;
maintain `_chartRegistry` (Map of canvas → `{chartInstance, platforms}`)
to track live instances; add a `MutationObserver` on
`document.documentElement` watching the `class` attribute. On toggle,
destroy and recreate every registered Chart instance with the current theme
colors.

**Known limitation**: `_chartRegistry` has no cleanup today because tool
cards are never removed from the DOM in normal use. When C6 (Save & Publish
with slide-in sidebar) is implemented, cards may become removable — review
registry cleanup at that point to avoid memory leaks.

### β — Real source status indicators

**Files**: `api/templates/base.html`, `api/routes.py`,
`war_room/clients/pulse_client.py`, `war_room/clients/release_agent_client.py`

Current header dots are hardcoded `bg-emerald-500` — always green regardless
of whether the MCP servers are reachable.

**Decisions (2026-04-30):**
- Single fetch at page load, no polling. If live refresh becomes necessary in
  practice, add later.
- Binary states: `ok` (green) / `unreachable` (red).
- Initial dot color: neutral grey. Updated when the fetch resolves. If the
  fetch itself fails (war-room API unreachable from browser), dots stay grey
  — not red, not green.
- Ping mechanism: `session.initialize()` over the real MCP transport
  (`streamable_http_client`). No dedicated health endpoint on external
  servers — war-room proxies via its own `GET /sources/status`. This tests
  the full end-to-end path the orchestrator uses.
- Both pings run concurrently via `asyncio.gather`; 3-second timeout each.
- If `PULSE_MCP_URL` / `RELEASE_AGENT_MCP_URL` are not configured, `ping()`
  catches the `KeyError` and returns `False` → dot shows `unreachable`
  (correct: the source is effectively unreachable from war-room's perspective).
- Rita: remains labelled "— soon", out of scope until rita integration lands.

---

## Phase 2b.2 — C6: Save & Publish flow

**Status**: active implementation (2026-05-02).

### Scope

Full Save & Publish UI. The backend (SavedInvestigationRepository, `POST
/conversations/{id}/publish`, `GET /investigations`, `DELETE /investigations/{id}`)
was built in C1. C6 wires the UI around it.

### Decisions (2026-05-02)

**Publish button**: already exists in `conversation.html` header; shown when
`ctx.current_hypothesis` is set. Currently opens a centred modal. C6 replaces
the modal with a right-panel slide-in sidebar.

**Sidebar layout**: Opció A — in-situ evolution of `x-data="{ publishing: false }"`
already on the outermost div of `conversation.html`. Width ~600px. Positioned
`absolute right-0 top-0 bottom-0` inside the `relative` parent. `x-transition`
translate-x (not opacity). Overlays the message thread.

**Preview content**: full conversation rendered inside the sidebar — same
`display_messages` loop used for the main thread (static HTML, server-rendered).
Includes tool cards (dot + label + chart if applicable). No filtering or
summarisation. If proved too long in practice, evolve later.
The hypothesis is NOT repeated separately at the end of the sidebar preview:
`display_messages` already contains it as the final assistant message. A
separate hypothesis block would duplicate content and risk visual divergence.

**Title field**: single editable field. Pre-filled from `saved_investigation.title`
if a prior publish exists, from `conversations.title` otherwise. No new DB column
or migration required — the implicit persistence through `saved_investigation.title`
achieves the desired "manual title survives republish" behaviour.

**Title edit on close**: if the user edits the title field and then closes the
sidebar (× button or backdrop click) without publishing, the edit is lost.
Accepted behaviour — title is persisted only on publish (implicit model). Not
a bug; a future reader should not interpret this as missing persistence logic.

**`/investigations` page**: new template + UI route (`GET /investigations/view`).
Link added to base.html header. Shows all saved investigations (title, author,
date, metrics) with per-row delete.

### Chart registry behaviour in sidebar (verified 2026-05-02)

`_chartRegistry` keys are canvas DOM elements; each `_applyCompletedState` call
creates a fresh canvas → unique key. Multiple canvases in the same page (main
thread + sidebar) coexist correctly.

The `MutationObserver` iterates the full registry: sidebar charts are destroyed
and recreated on dark/light toggle along with main-thread charts.

**Known sizing risk**: `x-show` hides with `display: none`. Sidebar charts are
initialised at `DOMContentLoaded` with 0-width parent. Chart.js@4's `ResizeObserver`
fires when Alpine restores `display` → charts resize before the slide-in
transition completes in practice. Verify empirically on first open.

**Double-submit guard**: `publishInvestigation()` already disables the confirm
button and sets text to "Publishing…" on click (re-enabled on error paths).
No change needed.

### Execution order

1. `docs/02-implementation/phase-plan.md` — this entry (commit)
2. `conversation.html` — modal → slide-in sidebar with preview + title edit
3. `base.html` — add "Investigations" link to header
4. `api/ui_routes.py` + `api/templates/investigations.html` — new route + template
5. Tests — smoke tests for new UI routes

Diff approval before each commit.

---

## Risk summary

| Phase | Controlled by | Primary risk |
|-------|--------------|--------------|
| 0 | War-room | None significant |
| 1a | War-room (spec) + Pulse + Release-agent (impl) | Spec-to-implementation mismatch on coverage metadata format |
| 1b | War-room | None significant |
| 2 | War-room, blocked by upstream | Length of the Phase 1a → Phase 2 interval; determined by upstream implementation pace |
| 3 | War-room | Streaming implementation; frontend framework decisions |
| 4 | War-room | Knowledge base calibration |

The dominant risk across the plan is the Phase 1a → Phase 2 interval: war-room is blocked by work it does not control. There is no technical workaround. Felip's active coordination across sessions is the only mitigation.
