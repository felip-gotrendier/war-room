# ADR-010: Orchestrator and skill invocation

**Status:** Accepted
**Date:** 2026-04-28
**Project:** war-room (Atlas Layer 3)

---

## Context

ADR-002 defines the iteration loop abstractly: each iteration is one LLM API
call, the cap is 15, the counter does not reset. This ADR defines how the loop
manifests in code: the conversation data structure, how Claude is called, how
MCP tools are dispatched, how skills are invoked, and how the 15-iteration
cap is enforced.

---

## Decisions

### 1 iteration = 1 Claude API call

**Decision**: `orchestrator.py` increments `iteration_count` exactly once per
call to `anthropic.messages.create()`. Tool execution (MCP adapter calls) does
not increment the counter.

Consequence: a single PM turn that triggers one MCP tool requires two Claude
calls (one to get the tool_use request, one to synthesize the tool result) =
two iterations. This is consistent with ADR-002's definition.

---

### Conversation as `list[dict]`

**Decision**: the conversation is a standard Claude API message list:

```python
[
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": [
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "check_metric", "input": {...}}
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    ]},
    ...
]
```

`ConversationContext` holds this list alongside metadata: `id`, `user_id`,
`iteration_count`, `current_hypothesis`, `created_at`, `last_active_at`.

For Phase 2a, `ConversationContext` objects live in a module-level dict in
`api/main.py`'s lifespan scope. No SQLite persistence. Phase 2b migrates this
to the `conversations` table (ADR-007).

---

### Tools exposed to Claude

**Decision**: war-room exposes exactly six tools to Claude, named to match
the upstream MCP servers:

| Tool name | Source | Input schema |
|-----------|--------|--------------|
| `check_metric` | pulse | `metric_name: str, days: int = 14, platform: str?` |
| `get_recent_anomalies` | pulse | `days: int = 7, severity: str?` |
| `trigger_scan` | pulse | *(no parameters)* |
| `get_releases` | release-agent | `repo: str, date_range: {start, end}` |
| `get_release` | release-agent | `repo: str, id: str` |
| `explain_release` | release-agent | `repo: str, id: str` |

Tool names are PROTECTED (ADR-011). The input schemas use the real server
parameter names (e.g., `metric_name` not `name`).

When a Claude response contains a `tool_use` block, the orchestrator resolves
the tool name to the appropriate adapter method and calls it. The result is
injected as a `tool_result` message before the next Claude call.

---

### Skills as prompt injection + output parsers

**Decision**: skills are not classes, subprocesses, or separate Claude
conversations. Each skill is implemented as:

1. A prompt markdown file at `skills/<name>/prompts/<name>.md`
2. A Python function in `war_room/skills/<name>.py` that:
   a. Loads the prompt file (at runtime, not import time)
   b. Constructs a skill-specific "user" message with relevant context injected
   c. (After Claude responds) parses the structured output from the message

Skills are invoked by appending a skill-specific message to the ongoing
conversation and calling Claude. The full investigation context — all prior
messages, findings, and tool results — is visible to Claude when a skill is
invoked. This is required: `hypothesis-formation` needs to reason over all
prior findings; `investigation-summary` needs to synthesize the entire session.

Rejected alternative — separate Claude call per skill with findings passed
explicitly: requires serializing all relevant context into each skill's input.
Fragile as investigations grow complex. The continuous conversation thread is
the correct model.

---

### Skill prompt section headers (PROTECTED)

**Decision**: the output parsers in `war_room/skills/*.py` extract structured
data from Claude's responses by matching section headers. These headers are a
parsing contract between the prompt files and the Python parsers. They are
PROTECTED per ADR-011.

| Skill | Protected headers |
|-------|-------------------|
| `funnel-investigation` | `Metric:`, `Window:`, `Coverage:`, `Findings:`, `Summary:` |
| `release-metric-correlation` | `Time window:`, `Repositories queried:`, `Coverage:`, `Candidate releases:` |
| `hypothesis-formation` | `Hypothesis:`, `Confidence:`, `Evidence for:`, `Evidence against:`, `What would confirm this:`, `What would refute this:`, `Next steps:` |
| `source-routing` | `Sources to query`, `The question requires` |
| `investigation-summary` | `## Investigation`, `## Findings`, `## Hypothesis`, `## Open questions` |

Renaming any of these headers requires simultaneous changes to the prompt
file and the parser. The process is the same as any PROTECTED decision: new
ADR, coordinated update.

---

### Skill dispatch: Claude-driven, orchestrator-guided

**Decision**: the orchestrator does not implement a rigid state machine that
prescribes the exact skill sequence. Instead, it guides Claude by injecting
skill-appropriate context at defined moments:

- **Conversation start**: system prompt = knowledge base (all sources, metrics,
  playbooks, ADR-004). The source-routing skill prompt is appended as the first
  user message alongside the PM's question.
- **After tool results are available**: the orchestrator continues calling
  Claude. Claude uses tools iteratively until findings are sufficient.
- **After findings are present and no pending tool_use**: the orchestrator
  appends the hypothesis-formation skill prompt.
- **On PM document request or publish action**: the orchestrator appends the
  investigation-summary skill prompt.

"Findings present" detection for Phase 2a: the orchestrator inspects Claude's
last text response for the presence of `Metric:` or `Candidate releases:`
markers (protected headers). When both a funnel finding and a release finding
are present (or a gap declaration for one), the orchestrator triggers
hypothesis-formation.

This approach is flexible: Claude can call multiple tools in sequence without
the orchestrator predicting the sequence. The skill injections are guardrails
that ensure the investigation converges toward a hypothesis.

---

### 15-iteration cap enforcement

**Decision**: before each call to `anthropic.messages.create()`:

```python
if context.iteration_count >= 15:
    raise IterationCapReached
```

The route handler catches `IterationCapReached`, appends a final system
message ("Investigation reached the 15-iteration limit — here is the current
state of findings"), and returns the conversation state to the PM. The
conversation becomes read-only: no further MCP calls, no new Claude calls.
The PM can publish from the existing hypothesis or open a new conversation.

---

### Knowledge base injection at conversation start

**Decision**: `war_room/knowledge_loader.py` reads the knowledge base files
and returns a structured system prompt string at conversation creation:

- `knowledge/sources/` — all source files → "Connected sources" section
  (per ADR-004)
- `knowledge/metrics/funnel-metrics.md` → metric definitions and benchmarks
- `knowledge/investigation-playbooks/metric-drop-release-correlation.md` →
  investigation pattern for the anchor use case
- `knowledge/repo-platform-mapping.md` → platform scope for release candidates

Injected once at conversation creation. Not re-injected per turn.

`knowledge_loader.py` is the sole entry point (ADR-011). No other module
reads files from `knowledge/` directly.

---

### Mock auth for Phase 2a

**Decision**: authentication uses a mandatory `X-User-Id` HTTP header. If
absent, routes return 401. No token validation. `user_id` is attached to
`ConversationContext` for scoping.

Google OAuth (ADR-005) and `authlib` are Phase 2b. Phase 2a's mock auth is
sufficient for anchor use case testing and is designed to be replaced without
changing any orchestrator or client logic — auth is enforced only at the
route handler layer.

---

## Consequences

**Positive**
- Continuous conversation thread makes full context available to every skill.
- No rigid state machine: Claude can adapt the investigation sequence to the
  PM's question.
- Skill dispatch points (start, after findings, on publish) are few and
  explicit; the rest is Claude's reasoning.

**Negative / trade-offs**
- Findings detection by header markers is heuristic. If Claude produces
  a malformed response (missing required headers), the parser degrades
  gracefully but may not trigger hypothesis-formation correctly. Robustness
  improves with prompt iteration in Phase 2.
- In-memory conversation store means conversations are lost on server restart.
  This is the accepted Phase 2a trade-off; Phase 2b adds SQLite.

**Constraints introduced**
- Skill prompt section headers are PROTECTED (ADR-011). Parser relies on
  exact header names.
- Findings detection by header marker matching is heuristic and depends on
  Claude producing exact PROTECTED headers. A more robust mechanism (e.g., a
  dedicated tool that Claude calls when investigation findings are sufficient)
  is deferred to Phase 2b. For Phase 2a, the heuristic is accepted with the
  understanding that a single response without exact headers may delay or skip
  hypothesis-formation injection.
- The 15-iteration cap is enforced before each Claude call, not before each
  PM turn. A PM turn that triggers multiple tool calls consumes multiple
  iterations.
- Mock auth (`X-User-Id`) is Phase 2a only. No user-facing documentation
  should describe it as the final auth model.

---

## Related decisions

- ADR-002 — iteration loop (1 call = 1 iteration; cap = 15)
- ADR-004 — knowledge base injection into system prompt
- ADR-007 — conversation schema (Phase 2b will persist what Phase 2a holds
  in memory)
- ADR-008 — `war_room/orchestrator.py` and `war_room/skills/` layout
- ADR-009 — adapter dispatch for tool_use blocks
- ADR-011 — PROTECTED decisions (skill headers, tool names)
