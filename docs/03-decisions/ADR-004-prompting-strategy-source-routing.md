# ADR-004: Prompting strategy for source routing

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

ADR-001 (Section 4b) identified `source-routing` as one of war-room's initial skills: given a PM's question, determine which sources are relevant and in what order. ADR-001 (Section 4f Case C) established that war-room's ability to declare unknown sources as out-of-scope is mechanically guaranteed via the knowledge base, not via prompting. This ADR defines concretely how the LLM learns which sources are available, how source descriptions are structured and delivered, how the LLM makes routing decisions, and how calls to unconnected sources are prevented.

This ADR covers the system-level setup for routing. The `source-routing` skill specification (Phase 1a.2) defines the in-session reasoning behavior: how the skill handles ambiguous questions, multi-source investigations, and graceful degradation when no source covers a question. These two documents are complementary and should be read together.

---

## Decisions

### Source descriptions live in the knowledge base

**Decision**: source descriptions are stored as structured markdown files in `knowledge/sources/`, one file per source. The orchestrator reads these files at session start and includes their content in the system prompt. Updating how a source is described — its scope, its tools, its limitations — is a knowledge base edit, not a code change.

This is an application of Atlas Principle 11 (knowledge as data). Source availability and capability are business facts, not code logic. When pulse gains a new tool (`trigger_scan`), adding it to war-room's understanding is a markdown edit to `knowledge/sources/pulse.md`.

Only connected sources appear in `knowledge/sources/`: a source file exists if and only if the corresponding MCP server is registered in war-room's tool set. The presence of a file is the signal that a source is available. This is the knowledge base layer of Case C enforcement.

Rejected alternative — source descriptions hardcoded in the system prompt at the code layer: updating descriptions requires a code change and deploy. Inconsistent with Principle 11 and the `pulse` ADR-013 precedent (the reasoning itself is data).

Rejected alternative — source descriptions derived automatically from MCP tool definitions: MCP tool definitions (name, parameter schema) are machine-readable but insufficient for routing. `get_recent_anomalies` tells the LLM it can call this tool; it does not tell the LLM when to prefer it over release-agent data or what it does not cover. Natural language descriptions fill this gap.

---

### Per-source description format

**Decision**: each file in `knowledge/sources/` follows this structure:

```markdown
# <source name>

**What it knows**: <2-3 sentences on scope and data coverage>

**What it does NOT know**: <1-2 sentences of explicit anti-patterns — what questions should NOT be routed here>

**Available tools**:
- `<tool_name>`: <one line — when to call this tool, not what it does mechanically>
- ...
```

The "What it does NOT know" field is mandatory. Without negative guidance, the LLM routes questions that look thematically relevant but are out of scope — for example, querying pulse for code change history because the question mentions metrics. Explicit anti-patterns reduce spurious queries.

Tool descriptions in the file describe *when to call*, not *what the parameters are*. Parameter schemas are in the MCP tool definition (ADR-003). The knowledge base description is for reasoning, not for call construction.

Rejected alternative — tool descriptions with examples: more helpful for complex tools but also more expensive in context tokens and harder to maintain. Start minimal; add examples to specific tools in the knowledge base if routing quality in real investigations proves insufficient.

---

### System prompt injection at session start

**Decision**: at session start, the orchestrator reads all files in `knowledge/sources/`, builds a "Connected sources" section, and injects it into the system prompt. The section includes:
1. One block per connected source, in the format above.
2. A closing instruction: *"Only query sources listed above. If answering a question requires data from a source not listed here, state this explicitly: 'To investigate this fully I would need [source], which is not currently connected.'"*

The closing instruction is the prompting component of ADR-001 Case C. It does not prevent Case C violations on its own — the tool registry does that — but it shapes the LLM's behavior toward explicit acknowledgment rather than approximation.

Session start is the only injection point. The source catalog does not change mid-session; new sources are not added while an investigation is in progress.

Rejected alternative — re-inject source descriptions before every LLM call: unnecessary token cost. The source catalog is stable within a session.

Rejected alternative — inject only the names of connected sources, not descriptions: the LLM needs to understand what each source covers to make good routing decisions. Names alone are insufficient.

---

### Multi-source queries within one iteration

**Decision**: the LLM may request tool calls to multiple sources in a single iteration. This is not prescribed — the LLM decides — but it is permitted and encouraged for queries that are genuinely independent.

When metric data and release history for the same time window are both needed, requesting them in parallel (one iteration) is faster than sequencing them (two iterations). The system prompt includes routing guidance: *"When two queries are independent — neither result would change whether you make the other query — request them together."*

Rejected alternative — single-source per iteration: forces sequential queries for independent data points. Increases investigation latency without benefit. The LLM is capable of recognizing independent queries.

---

### Unknown source rejection: dual-layer

**Decision**: calls to unconnected or unknown sources are rejected at two layers, consistent with ADR-001 Section 4f Case C:

**Layer 1 — Knowledge base**: unconnected sources have no file in `knowledge/sources/` and are not listed in the system prompt. The LLM is unlikely to propose a tool it has not been told about.

**Layer 2 — Tool registry**: even if the LLM requests an undefined tool call, the MCP client finds no registered server to handle it. The orchestrator catches the undefined tool at dispatch time and returns an `INVALID_PARAMS`-equivalent error to the LLM without retrying. The LLM sees this as a failed tool call and can acknowledge the missing source.

Layer 1 is the normal path. Layer 2 is the hard stop for edge cases. Together they ensure Case C is mechanically guaranteed, not prompt-dependent.

Rejected alternative — reject at Layer 1 only (prompt-based): prompting is not absolute (ADR-001 Section 4f, honest acknowledgment). A determined LLM can hallucinate tool calls. The tool registry provides a mechanical backstop.

---

## Consequences

**Positive**
- Updating source descriptions, adding anti-patterns, or adjusting tool guidance is a knowledge base edit. No code change, no deploy.
- The dual-layer rejection makes Case C a mechanical guarantee. War-room does not approximate answers from unavailable sources.
- Multi-source per iteration reduces investigation latency for the most common case (metric data + release history together).

**Negative / trade-offs**
- Source description quality directly affects routing quality. A poorly written `knowledge/sources/pulse.md` (missing anti-patterns, vague tool descriptions) will produce spurious queries. This is a content maintenance responsibility, not a code problem.
- The "What it does NOT know" field requires the team to think through anti-patterns proactively when connecting a new source. There is no automated way to discover what a source does not cover.
- The system prompt grows with each connected source. At MVP (two sources) this is negligible. At ten connected sources it may become significant. A pruning strategy (inject only source descriptions relevant to the current question) is deferred — not needed at MVP and would add complexity.

**Constraints introduced**
- `knowledge/sources/` is the authoritative registry of connected sources. Adding a source to war-room requires: (1) implementing its MCP server, (2) registering it in the tool set, and (3) creating a `knowledge/sources/<name>.md` file. All three steps are required; partial completion leaves the source unavailable or undescribed.
- The closing instruction in the system prompt ("only query sources listed above") must be present. Removing it weakens the Case C prompting guarantee.
- Source descriptions are written for the LLM, not for human readers of the knowledge base. They should be authored accordingly: precise, without hedging, written in the second person as instructions.

---

## Related decisions

- ADR-001 Section 4b — `source-routing` as an initial skill; knowledge base as the home of business knowledge
- ADR-001 Section 4f Case C — unknown source rejection as a mechanical guarantee via knowledge base
- ADR-002 — the loop that executes routing decisions and receives tool results
- ADR-003 — tool signatures and descriptions that knowledge base files complement
