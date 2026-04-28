# ADR-009: MCP client design

**Status:** Accepted
**Date:** 2026-04-28
**Project:** war-room (Atlas Layer 3)

---

## Context

War-room calls two external MCP servers (pulse, release-agent) and is designed
to integrate a third (bi-tool, a BI query service under development) when its
contract is published. The two active servers diverge in their response
envelope shapes, parameter naming conventions, and error structures. This ADR
defines how war-room connects to MCP servers, normalizes their responses, and
handles errors and retries. It also establishes the three-source architecture
so that bi-tool integration is additive when the server becomes available.

---

## Decisions

### Transport: `streamablehttp_client`, stateless per tool call

**Decision**: each tool invocation opens a new `streamablehttp_client` context
from the `mcp` SDK, calls the tool, and closes the connection. No persistent
MCP session is maintained between calls.

```python
from mcp.client.streamablehttp import streamablehttp_client
from mcp import ClientSession

async with streamablehttp_client(url) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(name, arguments)
```

Both pulse and release-agent use `stateless_http=True`. Each call is an
independent HTTP request by design on the server side; opening a new context
per call is the correct client behavior.

Rejected alternative — direct `httpx` with manual JSON-RPC encoding: bypasses
SDK protocol handling; fragile against SDK version changes.

---

### Per-source adapter pattern

**Decision**: `war_room/clients/pulse_client.py` and
`war_room/clients/release_agent_client.py` each implement a typed async
interface. The orchestrator never imports or calls the `mcp` SDK directly —
it only calls adapter methods. The adapter handles:

1. Parameter translation (war-room internal → wire format)
2. MCP tool call via `streamablehttp_client`
3. Response normalization (wire format → internal `WarRoomFinding`)
4. Coverage synthesis when absent (see below)
5. Retry policy enforcement

This pattern is designed for three sources. When bi-tool's MCP contract is
published, adding `war_room/clients/bi_tool_client.py` following the same
pattern is the complete integration. No orchestrator changes and no
source-routing rewrite are needed.

---

### Three-source architecture: pulse, release-agent, bi-tool

**Decision**: war-room is designed for three MCP sources. At Phase 2a,
two clients are implemented; the third is prepared architecturally.

**Pulse** covers predefined funnel metrics with deep analytical context:
anomaly detection, rolling baselines, time-series of the canonical purchase
funnel stages. It does not cover ad-hoc DB queries, metrics outside the
defined funnels, or arbitrary dimensions.

**Release-agent** covers release history and release narratives for
confirmed production repositories.

**Bi-tool** (under development) will cover ad-hoc DB queries beyond
pulse's predefined funnels: different metrics, different dimensions, custom
time windows not aligned with pulse's scanning cadence. Its role complements
pulse rather than replacing it — pulse provides depth on canonical metrics;
bi-tool provides breadth for non-canonical queries.

At Phase 2a, bi-tool integration manifests as:
- `knowledge/sources/bi-tool.md` (new): documents bi-tool's anticipated
  scope and routing patterns, marks status as "MCP server in development —
  invocation deferred until contract is published"
- `knowledge/sources/pulse.md` (updated): adds explicit scope boundary —
  "for queries outside predefined funnels, see bi-tool.md"
- `knowledge/sources/release-agent.md`: no change needed

When bi-tool's MCP server is ready: complete `knowledge/sources/bi-tool.md`
with tool signatures, add `war_room/clients/bi_tool_client.py`.

---

### Pulse parameter translation

**Decision**: pulse uses `metric_name: str` and `days: int` (not `name` and
`window: {start, end}` as the Phase 1 spec described). War-room's skills
reason in terms of a conceptual "window", but the pulse adapter translates
internally:

- Named duration ("last 7 days") → `days=7`
- Window dict `{start, end}` → `days = (end - start).days`

No `window` object is ever sent to pulse. This is a known divergence between
the Phase 1 spec (`docs/specs-for-external-sessions/pulse-mcp-spec.md`) and
the production pulse server. The spec is corrected in a separate commit during
Phase 2a.

Similarly: `get_recent_anomalies` uses `days: int` and `severity: str | None`,
not `window`.

---

### Response normalization and envelope divergence

**Decision**: pulse and release-agent diverge significantly in response shape:

| Aspect | Pulse | Release-agent |
|--------|-------|---------------|
| Success wrapper | `{"data": {...}, "coverage": {...}}` | `{"releases": [...], ...}` / `{"release": {...}, ...}` / `{"explanation": {...}, ...}` — no `data` wrapper |
| Error format | `{"error": "...", "coverage": {...}}` | `{"error": {"code", "retryable", "message", "requested"}}` — no `coverage` |

Each adapter normalizes to internal structures. The orchestrator receives
`WarRoomFinding` objects, never raw wire responses.

**`coverage.requested` and `coverage.covered` as strings**: war-room's
internal `Coverage` dataclass uses `str` for both fields, consistent with
pulse's implementation. ADR-003 specified structured objects for programmatic
comparison; this was aspirational and not implemented by either upstream server.
No war-room component performs programmatic comparison of `requested` vs
`covered`. If structural comparison is ever needed, it requires upstream schema
changes and a war-room migration. This is a known limitation, not an oversight.

---

### Coverage synthesis for absent coverage

**Decision**: when release-agent returns an error without a `coverage` field
(its current behavior), the adapter synthesizes:

```python
Coverage(
    requested=str(requested_params),
    covered="",
    is_complete=False,
    gaps=[f"release-agent error: {error_code}"]
)
```

The invariant "every internal finding has a Coverage object" holds regardless
of upstream behavior. The orchestrator and skills never check for None coverage.

---

### Retry policy

**Decision**: 1 retry per MCP tool call on retryable errors. No further retries.
Applies to all adapters uniformly. Non-retryable error codes propagate immediately:

| Source | Non-retryable codes |
|--------|---------------------|
| Pulse | `AUTH_FAILURE`, `INVALID_PARAMS`, `DATA_NOT_FOUND` |
| Release-agent | `REPO_NOT_FOUND`, `RELEASE_NOT_FOUND`, `INVALID_DATE_RANGE` |

`REPO_NOT_FOUND` from release-agent is treated as a coverage gap (not a
system error): the adapter constructs a finding with `is_complete=False` and
`gaps=["No confirmed repositories available — release-agent risk maps pending
tech lead validation"]`. This is the expected state during Phase 2a until
production repos are confirmed.

---

### `trigger_scan` integration

**Decision**: `trigger_scan()` is included in the Phase 2a tool set.

Wire behavior: no parameters, returns `{"data": {"scan_accepted": True,
"message": "Scan triggered."}}` immediately. No `scan_id`. Asynchronous
on the pulse side.

Adapter behavior:
1. Records `triggered_at = datetime.now(timezone.utc).isoformat()` locally
2. Returns to the orchestrator: `{"scan_accepted": True, "triggered_at": "<ISO>",
   "note": "Fresh data available in ~60 seconds via get_recent_anomalies."}`

War-room presents to PM: "Scan triggered at HH:MM:SS UTC. Fresh data will be
available via get_recent_anomalies in approximately 60 seconds."

War-room does not poll. The PM can re-invoke `get_recent_anomalies` in the
current conversation after waiting, or in a new conversation. This is the
correct behavior: the PM controls when to check, war-room does not block.

Primary invocation signal: `get_recent_anomalies` returns coverage gaps for
the investigation's time window AND the PM's question requires fresh data for
a substantive answer. Claude decides whether to trigger; war-room executes.

---

## Consequences

**Positive**
- Orchestrator is isolated from MCP transport details; adapters are the
  single point of change for upstream contract changes.
- Three-source architecture is ready for bi-tool without orchestrator changes.
- Coverage invariant holds regardless of upstream behavior.
- `trigger_scan` is available for cases where fresh data materially affects
  the investigation.

**Negative / trade-offs**
- Two separate adapters mean two separate normalization implementations.
  Divergence between pulse and release-agent justifies this; a shared base
  class would paper over meaningful differences.
- `coverage.requested/covered` as strings limits future programmatic
  comparison. Acknowledged as a known limitation.
- `REPO_NOT_FOUND` graceful handling means Phase 2a cannot correlate
  real releases until tech lead confirms production repos in release-agent.
  This is a known external dependency, not a war-room code issue.

**Constraints introduced**
- No direct `mcp` SDK imports in `war_room/orchestrator.py` or
  `war_room/skills/`. Only adapter modules import from `mcp.client`.
- MCP tool names are PROTECTED (ADR-011). Renaming requires coordinated
  change with upstream servers.
- The pulse spec correction (`metric_name`, `days` vs `name`, `window`) must
  be applied in a Phase 2a commit.

---

## Related decisions

- ADR-002 — iteration loop; 1 retry per MCP call
- ADR-003 — WarRoomResponse envelope (aspirational; actuals documented here)
- ADR-008 — package layout (`war_room/clients/`)
- ADR-010 — orchestrator dispatches to adapters, never to MCP SDK directly
- ADR-011 — MCP tool names are PROTECTED
