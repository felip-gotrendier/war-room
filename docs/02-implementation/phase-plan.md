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
