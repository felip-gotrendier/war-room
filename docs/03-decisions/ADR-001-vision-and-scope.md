# ADR-001: War-room — vision, scope, and core architecture

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

Atlas has two active layers in the release-work triad. `release-agent` (Layer 1) analyzes every release as it ships: it scores risk, detects A/B tests, and notifies the team when something dangerous has gone out. `pulse` (Layer 2) monitors business metrics continuously and alerts when something deviates from normal. Both are reactive and push-oriented — they answer well-defined questions triggered by well-defined events.

PMs at GoTrendier regularly face a structurally different class of problem: open-ended investigations with no obvious trigger and no single authoritative source.

- *"Sales feel low — can you tell me what might be happening?"*
- *"What was pushed to production since April 15, and could it have affected sales?"*
- Any cross-cutting question that requires consulting multiple systems and synthesizing the answer.

Neither `pulse` nor `release-agent` addresses these. `pulse` reports what it detected; it does not follow a PM's hypothesis. `release-agent` analyzes releases as they ship; it does not answer retrospective queries on demand. Today the PM resolves these questions manually — multiple browser tabs, Slack messages to colleagues, Jira searches, mental correlation under pressure. The investigation is slow, inconsistent, and not preserved.

`war-room` is Layer 3 of the release-work triad: the interactive investigation agent that closes this gap.

The construction phase plan for war-room is maintained as a separate document and is not embedded in this ADR.

---

## Vision

War-room is a web-based conversational agent where PMs at GoTrendier conduct open-ended incident investigations guided by evidence.

When a PM brings a question — from a `pulse` alert, a team intuition, an observed metric drop, or any other entry point — war-room performs an initial scan of connected sources, forms a first hypothesis, and proposes an investigation path. The conversation proceeds with **hybrid initiative**: war-room investigates and synthesizes; the PM can redirect at any point. War-room is honest about the limits of what it can conclude with its connected sources.

War-room integrates the Atlas ecosystem progressively. At MVP it consults two sources: `pulse` (funnel metrics, anomaly scans) and `release-agent` (release history, code analysis). The architecture accommodates additional sources as they come online — Datadog, Cloudflare, `product-memory`, `support-digester` — without modifying the core reasoning loop.

War-room maintains explicit memory. When a PM considers an investigation closed, they can save it as a structured artifact. Saved investigations are visible to the whole team and retrievable in future sessions by any user, forming a cumulative shared record of past incidents, hypotheses, and findings.

The output of an investigation is the conversation itself during the session. When the PM requests it, war-room produces a structured document summarizing findings, evidence, and open questions. The document is the deliverable; the conversation is the process.

---

## MVP completeness criteria and anchor use case

**MVP completeness criteria**

War-room reaches MVP when it demonstrates all five capabilities:

1. **Metric investigation**: given a metric name and a suspected time window, retrieve `pulse` data, identify when the deviation started, quantify it, and describe it across platforms.
2. **Release correlation**: given a time window, retrieve release history from `release-agent`, identify releases that overlap with the deviation, and describe what changed.
3. **Hypothesis formation**: synthesize findings into a plausible hypothesis linking a cause to an observed effect, with explicit confidence framing and named contrary evidence.
4. **Directed investigation**: accept PM redirection mid-investigation ("did you check X?", "focus on platform Y") and adjust accordingly without restarting from scratch.
5. **Scope honesty**: when the investigation requires a source that is not connected, declare this explicitly — what the source would contribute, and why war-room cannot proceed without it. Do not approximate from available data.

**Anchor use case**

The following real GoTrendier question, as of this ADR's date, is the concrete validation test for the five capabilities:

> *"Tenim la sensació que les vendes estan baixes. Hem vist que `users_product_list/active` ha caigut. Pots ajudar-me a investigar què passa?"*
>
> *(English: "We feel like sales are low. We've seen that `users_product_list/active` has dropped. Can you help investigate what's happening?")*

With MVP sources, war-room should: retrieve `pulse` data to quantify and locate the `product_list` drop across platforms; retrieve release history for the relevant window; form a temporal correlation hypothesis with explicit confidence framing; accept PM redirection; and acknowledge explicitly when confirming the hypothesis would require a source not yet connected (e.g., Datadog logs, database queries).

The anchor use case is evidence, not a definition. Handling it well with real data is the strongest available signal that the MVP is complete. Failing it conclusively indicates the MVP is not.

---

## Architectural decisions

### Interface: web-based chat

**Decision**: war-room's primary interface is a web-based chat application, not Slack.

This is an explicit, documented deviation from Atlas Principle 4 ("Slack as the primary interface"). Principle 4 permits tool-level deviation when a tool-level ADR explains why Slack is insufficient for the use case. This is that explanation.

Four structural arguments specific to war-room:

**1. Investigation length and navigation.** A war-room investigation is a multi-turn conversation spanning dozens of exchanges, tool results, and hypothesis revisions. Slack threads degrade past approximately twenty exchanges: no search within a thread, no scroll to a specific earlier exchange, no inline reference to context from several turns back. The PM needs to navigate an investigation as a document, not a channel thread.

**2. Session state and lifecycle.** An investigation has an explicit lifecycle: open, in-progress, closed, saved, discarded. Slack has no model for this. A bot conversation in a channel is always open from Slack's perspective, with no affordance for marking an investigation complete or archiving it.

**3. Memory affordances.** The explicit save mechanism requires UI that Slack cannot provide: a save action, a browsable list of shared investigations, retrieval, team-visible artifacts. These interactions do not map to a bot command model.

**4. Agent UX versus bot UX.** War-room is a sustained reasoning partner, not a notification surface. The interaction model — long thinking pauses during tool calls, iterative hypothesis building, deliberate mid-investigation redirection — fits a focused dedicated interface, not a channel shared with ongoing team communication.

Rejected alternative — Slack interface: `atlas-docs/02-tools/war-room.md` currently describes Slack as the interface. This ADR supersedes that description for this architectural dimension. The arguments above are specific to war-room; they do not challenge Principle 4 for other Atlas tools.

Follow-up (out of scope for this ADR): `atlas-docs/01-vision/principles.md` and `atlas-docs/02-tools/war-room.md` should be updated to document this exception. This is an ecosystem-level coordination task for Felip, not a war-room-level decision.

---

### Internal structure: orchestrator + skills + knowledge base

**Decision**: war-room adopts the orchestrator + skills + knowledge base pattern established by `pulse`.

The orchestrator is a thin control layer: it reads the knowledge base, determines which skills to invoke, and assembles the response. Skills are discrete, documented investigation behaviors — each defined as a markdown specification describing what the skill does, what sources it consults, and what it returns. The knowledge base contains business knowledge that anyone on the team can edit without touching code: source definitions, investigation playbooks, GoTrendier metric context, seasonality patterns, anchored investigation heuristics.

The LLM interpretation logic — what constitutes a meaningful hypothesis, how to frame uncertainty, when to propose a redirect — lives in the knowledge base as markdown, not in Python. This is consistent with `pulse` ADR-013 (prompt-as-markdown): the reasoning itself is data.

**Initial skill candidates** (not a closed list — subject to revision in the implementation ADR):

- `release-metric-correlation`: given a metric deviation and a time window, retrieve relevant releases from `release-agent` and identify temporal overlaps.
- `funnel-investigation`: query `pulse` for funnel metric data, identify anomalies, quantify deviations, surface platform-level detail.
- `hypothesis-formation`: synthesize findings from consulted sources into a structured hypothesis with explicit confidence framing and named contrary evidence.
- `source-routing`: given the PM's question, determine which sources are relevant and in what order — translating natural language intent into tool calls.

Skills do not call each other. They are invoked by the orchestrator and assembled into a response. This is the same discipline as `pulse`'s skills model.

Rejected alternative — custom ad hoc architecture: building war-room as a single LLM call with all tool definitions inline is faster for the first iteration, but collapses the distinction between investigation logic and business knowledge. When GoTrendier's context changes — new metrics, revised thresholds, new investigation playbooks — it forces code changes instead of knowledge base edits. This is the pattern `release-agent` established inadvertently and that new tools must not repeat (Principle 11).

---

### Reasoning model: multi-step iterative tool use

**Decision**: war-room reasons by iterating tool calls. The LLM decides what source to consult, receives the result, decides the next step, and continues until it has enough to respond or a termination condition is reached.

This mirrors how a human investigator works: each finding shapes the next question. A single metric query may reveal an unexpected platform-specific pattern that redirects which releases to examine.

Termination conditions (concrete shapes deferred to implementation ADR): max iterations reached; LLM signals sufficient evidence to respond; PM intervenes with a redirect that restarts a branch; a tool failure leaves no productive path forward.

Rejected alternatives:
- **Single-pass tool use** (all calls decided upfront before any result is seen): too rigid for genuine investigation. The second query typically depends on what the first found.
- **Agent frameworks** (LangGraph, CrewAI, similar): consistent with the precedent established by `release-agent` ADR-001 and Atlas Principle 3. Direct orchestration is sufficient at this scale; framework abstraction cost is not justified.

---

### Source integration: MCP

**Decision**: war-room integrates all sources exclusively via MCP. Source adapters are MCP clients consuming MCP servers.

At MVP, war-room consumes two MCP servers: `pulse` and `release-agent`. Future sources enter the ecosystem by implementing a new MCP server. The core reasoning loop is not modified.

MCP exposure is at tool level, not skill level. `pulse` exposes `get_recent_anomalies()`, `check_metric()`, and `trigger_scan()` — not the internal `funnel-scan` skill. `release-agent` exposes release query tools — not its internal analysis pipeline. This is the default established in `mcp-strategy.md`: skills are implementation details of a source tool; the tool's public interface is its MCP server. Internal restructuring of a source tool must not break war-room.

This decision is consistent with `atlas-docs/01-vision/mcp-strategy.md`, which explicitly identifies war-room as the archetypal MCP-consuming agent and recommends Layers 2 and 3 as the natural entry point for MCP adoption in Atlas.

Rejected alternatives:
- **Custom adapters per source**: solves the immediate problem but produces N × M integration maintenance as sources and tools multiply — the problem `mcp-strategy.md` identifies directly.
- **Direct API calls from the reasoning loop**: hardcodes source-specific knowledge (authentication, endpoints, schema) in the orchestrator. Every source change requires an orchestrator change.

---

### Memory: explicit, PM-controlled, team-visible

**Decision**: war-room saves investigations only when the PM explicitly marks them as saved. Active (unsaved) investigations are private. Saved investigations are shared with the entire team.

**Active investigations** are private to the user who created them, identified by their Google login (see Authentication). No cross-user visibility during an in-progress investigation. A PM's working hypothesis, dead ends, and redirections are theirs until they decide the investigation is worth preserving.

**Saved investigations** are visible to any user with access to war-room. The act of saving is simultaneously an act of publishing. There is no intermediate state of "saved but private." When a PM marks an investigation saved, war-room synthesizes the conversation into a structured artifact (schema deferred to the Phase 1b ADR covering memory, visibility, and authentication); from that point it is part of the team's shared record.

**Deletion rights**: any war-room user can delete any saved investigation, regardless of who created it. War-room investigations are working artifacts — tools the team uses to understand incidents — not institutional records with authorship obligations. The model is team trust by default. If the team's working context changes (larger team, external access, higher-stakes artifacts), this policy is revisable through an ADR.

**Team protocol (not enforced by code)**: "Only save what merits sharing." Curation is the team's responsibility. The system does not prevent over-saving; the protocol does.

Integration with `product-memory` is explicitly out of scope for the MVP. When `product-memory` exists, two integration paths are possible: `product-memory` reads war-room's saved investigations as a source, or war-room routes appropriate content to `product-memory`. That decision will be made when `product-memory` exists. This ADR neither precludes nor commits to either path.

Rejected alternatives:
- **Private-only memory**: each PM has an isolated memory store, invisible to others. Eliminates the institutional value of accumulated team knowledge of past incidents — the central long-term proposition of the memory feature.
- **Three-state visibility** (private / saved-private / saved-public): more granular, but introduces a permissions matrix without practical justification at current team size and tool maturity. Addable later if demonstrated necessary.
- **Author-only deletion**: would prevent accidental deletions by others, but creates edge cases (what happens when the author leaves the company?) and bureaucratic overhead that exceeds the benefit. The team-trust model avoids this.
- **No memory**: every session is isolated. Forces re-explanation of context on every return; eliminates the institutional value of past investigations.
- **Automatic memory**: every conversation is retained. No signal distinguishes what mattered from what did not, with management burden and no proportional value.

---

### Honesty about scope

**Decision**: war-room explicitly declares the limits of what it can answer with its connected sources. The strength of this guarantee varies by failure case.

**Case A — source unreachable** (MCP call fails: server down, error response, timeout):
War-room halts the affected investigation branch and surfaces the failure visibly. The PM decides whether to retry, redirect, or stop.
→ *Mechanical guarantee.* Orchestrator behavior independent of prompting. The code detects and surfaces the failure.

**Case B — source returns incomplete or partial data** (pulse responds but the last two days have no scan; release-agent has a gap in a date range):
War-room continues the investigation but distinguishes explicitly: "this is what I know from available data" versus "this is what I am missing, and the reason is X."
→ *Prompting guarantee, conditional on a structural prerequisite.* War-room's ability to explain *why* data is missing depends on sources returning coverage metadata alongside their data — not just results, but also: which platforms were covered, which time windows were scanned, whether data is live or stale, any known gaps. This is a constraint that war-room imposes on its MCP sources. The coverage metadata format is specified in the MCP contract ADR (Phase 1a) and is a hard dependency alongside the tools themselves (see Hard MVP dependencies).

**Case C — capability outside connected sources** (PM asks about user reviews when `support-digester` is not connected):
War-room knows its connected sources from the knowledge base and states the gap explicitly, without attempting to approximate from available data.
→ *Mechanical guarantee via knowledge base.* Connected sources are knowledge base data, not prompt content. If a capability is not in the knowledge base, the orchestrator does not attempt it.

**Acknowledgment of limits**: Cases A and C are mechanically guaranteed. Case B relies on prompting plus source cooperation. Prompting is not absolute — `release-agent`'s deterministic risk floor is the Atlas precedent for why behavioral guarantees via prompting alone are weaker than mechanical ones. Mitigations (prompt hardening, automated checks for claimed-but-missing coverage metadata) are deferred to a later ADR.

**War-room does not privilege Atlas sources as authoritative.** `Pulse` and `release-agent` are cited sources, not oracles. War-room always attributes explicitly: "pulse reports X", not "X is true". If `pulse` has uncalibrated detection or `release-agent` misclassifies a release, the PM must be able to question the source without war-room resisting. Explicit attribution is the defense against bugs in upstream layers that have not yet been externally stressed.

This principle is a direct consequence of the construction decision: war-room is being built before `pulse` and `release-agent` have been validated by users beyond Felip. The tradeoff is explicit — faster construction in exchange for more responsibility in how source output is framed.

---

### Authentication

**Decision**: war-room requires login via Google. No domain restriction for now.

War-room exposes sensitive GoTrendier data: release history, anomaly scans, the internal knowledge base, and accumulated team investigations. Authentication is required before any web deployment. Google login is the option with the lowest friction given that the entire team already operates with Google accounts.

No domain restriction is applied at MVP. This is a conscious decision: restricting access to a specific Google Workspace domain is an incremental addition that does not change the authentication model. If the tool's exposure grows beyond the current team, the restriction is addable through configuration without an architectural change.

Rejected alternatives:
- **No authentication**: acceptable only for local development. Not acceptable for any networked deployment, given the data war-room exposes.
- **Full enterprise SSO**: over-engineering for the MVP given the current scope of the tool (a single team, a validating audience of one) and the current state of the ecosystem. Revisable if deployment context changes.

---

## Sources

**MVP — two sources**

- **`pulse`** — funnel metric scans, anomaly history, per-platform metric data. Queried via MCP with `get_recent_anomalies()`, `check_metric()`, and `trigger_scan()`. Must return coverage metadata alongside data (see Hard MVP dependencies).
- **`release-agent`** — release history, risk analysis, code change descriptions. Queried via MCP in on-demand mode with `get_releases()`, `get_release()`, and `explain_release()` (see Hard MVP dependencies).

**Out of scope for MVP**

Datadog, Cloudflare, internal database query tooling, App Store / Play Store review digests, communication channel metrics. The architecture must accommodate these without rearchitecting. Adding a source is implementing an MCP server and a knowledge base entry for that source.

**Future Atlas ecosystem sources**

- **`product-memory`**: "has a similar incident happened before?", "who last owned this metric?". Consumed via MCP when `product-memory` exists.
- **`support-digester`**: "what are users saying about this area right now?". Consumed via MCP when `support-digester` exists.

---

## Hard MVP dependencies

War-room cannot ship its MVP without two changes to upstream Atlas tools. Both are outside the war-room repository and require dedicated ADRs in their respective repositories.

**Dependency 1 — Pulse MCP server with `trigger_scan` and coverage metadata**

`Pulse` must expose a stable MCP server with at minimum:
- `get_recent_anomalies(window)` — anomalies detected in a time window
- `check_metric(name, window)` — metric data for a specific metric and window
- `trigger_scan(platform, date_range)` — run a scan on demand rather than waiting for the next scheduled run

`trigger_scan` is a new capability for `pulse`; it does not exist today. All tools must return coverage metadata sufficient for Case B honesty: which platforms were covered, which time windows were actually scanned, whether data is from a live sync or a stale cache, any known gaps. Without this metadata, war-room can only report "some data was missing" rather than explaining why — a weaker form of the guarantee than Case B requires.

The complete MCP contract specification — tool signatures, coverage metadata schema, error codes — is a Phase 1a deliverable from war-room, produced as input for the `pulse` session to implement.

**Dependency 2 — Release-agent on-demand mode**

`Release-agent` currently runs reactively: a release ships and analysis runs. War-room must query it actively:
- `get_releases(repo, date_range)` — list releases for a repository in a time window
- `get_release(repo, id)` — full report for a specific release
- `explain_release(repo, id)` — narrative of what changed and why the release was scored as it was

This requires a dedicated ADR in the `release-agent` repository. The specification is a Phase 1a deliverable from war-room.

**"Pulse in production" criterion for this ADR**: `pulse` is considered production-ready for war-room's purposes when it is functional and its MCP server is stable — not when it has been validated by users beyond Felip. This is a deliberate decision: waiting for external validation of Layer 2 before starting Layer 3 would delay the ecosystem unnecessarily when both layers are evolving in parallel and Felip is the primary user of all three.

**Coordination cost**: both dependencies require work outside war-room's control. Phase 2 of war-room cannot start until both are available. The interval between Phase 1a completion and Phase 2 start is a real scheduling risk. There is no technical workaround — Felip's active coordination across sessions is the only mitigation.

---

## MVP scope

**In scope**

- Web chat UI — functional for Felip's use, not polished for a wider team
- FastAPI backend serving sessions (Python/FastAPI, Atlas convention)
- Multi-step iterative reasoning loop with explicit termination conditions
- Orchestrator + skills + knowledge base structure, with initial skill set
- Two source adapters via MCP: `pulse`, `release-agent`
- Five MVP capabilities as defined in the completeness criteria
- Google login authentication
- Memory: explicit PM-controlled save; shared visibility for saved investigations; team-wide deletion rights
- Structured investigation document as output, on PM request
- All three honesty cases (A, B, C)

**Out of scope for MVP**

Sources beyond `pulse` and `release-agent`; `product-memory` integration; `support-digester` integration; cross-tool memory access; multi-user permission granularity beyond the current model; domain restriction on Google login; polished UI; mobile or desktop apps; proactive behavior of any kind; Slack integration. The architecture must not preclude any of these — they are simply not built.

---

## Deferred decisions

The following are acknowledged but not decided in this ADR:

- **Iteration loop implementation**: termination conditions, max steps, retry logic, error handling within the loop — implementation ADR (Phase 1a)
- **MCP contract for sources**: full tool signatures, coverage metadata format, error codes — MCP contract ADR (Phase 1a)
- **Prompting strategy for source routing**: how the LLM selects and sequences sources — prompt design ADR (Phase 1a)
- **Memory schema, visibility model, and authentication implementation**: storage backend, structured artifact schema, Google OAuth implementation details — single ADR covering all three (Phase 1b; see phase plan for rationale)
- **Investigation document format**: sections, generation logic, format — format ADR (Phase 1b, analogous to `pulse`'s scan-report-format)
- **Session persistence**: database, in-memory store, session lifecycle — infrastructure ADR (Phase 1b)
- **Frontend tech stack**: framework choice deferred — implementation ADR; do not pre-commit
- **Backend tech stack**: Python/FastAPI is the Atlas convention and the default; deviation requires a dedicated ADR
- **`release-agent` on-demand mode**: specification and implementation — ADR in the `release-agent` repository (Phase 1a coordination)
- **`product-memory` integration path**: deferred until `product-memory` exists; this ADR neither precludes nor commits to any specific integration
- **Google Workspace domain restriction**: addable through configuration when and if the tool's audience grows beyond the current team; not an architectural decision
- **Atlas-docs ecosystem amendments**: Principle 4 exception and `war-room.md` update — Felip's ecosystem coordination, not a war-room-level decision

---

## Consequences

**Positive**

- War-room is positioned from day one as the integration point of the Atlas ecosystem. The MCP-based source architecture means new sources compose without rearchitecting the core reasoning loop.
- The five capabilities in the completeness criteria give a concrete, falsifiable MVP definition. There is no ambiguity about when the first usable version is done.
- The orchestrator + skills + knowledge base pattern means investigation logic, prompts, and GoTrendier business context are editable without code changes. When a metric is redefined or a seasonal pattern is identified, it becomes a knowledge base edit.
- Explicit attribution ("pulse reports X", not "X is true") makes war-room's reliability transparent and builds trust progressively, rather than projecting confidence that erodes when upstream layers show calibration gaps.
- The shared-visibility memory model creates a compounding institutional record: every saved investigation is immediately useful to the whole team, without the overhead of a permissions system.

**Negative / trade-offs**

- The MVP scope is the most ambitious of any Atlas tool so far: web UI, iterative reasoning, MCP integration, authentication, and shared memory — all in the first version. Time to first usable version is measured in weeks, not days.
- Two hard external dependencies (pulse MCP server with `trigger_scan` and coverage metadata; release-agent on-demand mode) mean a portion of the war-room timeline is outside war-room's control. The primary risk is not technical — it is the interval between Phase 1a completion and Phase 2 start, determined by how quickly upstream sessions implement their side.
- The Principle 4 deviation introduces a workflow friction point: when a `pulse` alert fires in Slack, the PM must switch to the browser to investigate with war-room. This is a deliberate trade-off, not an oversight.
- Case B honesty quality is bounded by upstream quality. If `pulse` or `release-agent` does not return rich coverage metadata, war-room degrades from specific gap explanations to vague ones.
- The team-wide deletion model is a trust assumption. If that trust assumption breaks (larger team, external access, adversarial actors), an ADR revision is required.

**Constraints introduced**

- Any source integrated into war-room must implement a conforming MCP server. Direct API integration from the reasoning loop is not allowed.
- Saved investigations must be structured artifacts at save time, not raw conversation transcripts. The synthesis step is required at save time so that future readers can rely on a stable schema.
- Skills must not call each other directly. They are orchestrated, not chained.
- `release-agent`'s on-demand mode is a hard dependency for capability 2 (release correlation). War-room cannot demonstrate the anchor use case without it.
- `pulse`'s `trigger_scan` and coverage metadata are hard dependencies for capabilities 1 and 5. A `pulse` MCP server that exposes only historical anomaly reads is not sufficient.
- War-room does not attempt to answer questions that require unconnected sources. A source must have a knowledge base entry before the orchestrator will attempt to query it. This prevents "source not found" failures from manifesting as empty or hallucinated answers.
- Any war-room user can delete any saved investigation. This is an explicit team-trust policy, not a missing access control. If the team's working context changes, this policy is revisable through an ADR.
