# ADR-003: MCP contract for war-room sources

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

ADR-001 (Section 4d) established that war-room integrates all sources exclusively via MCP, and Section 4f Case B established that honesty about partial data depends on sources returning coverage metadata alongside their data. This ADR defines the generic contract — tool signature form, response envelope, coverage metadata structure, and error vocabulary — that any source consumed by war-room must fulfill. It is the foundation on which Phase 1a.4's concrete specifications for pulse and release-agent will be built.

---

## Decisions

### Generic tool signature form

**Decision**: a war-room-compatible MCP tool has four required elements:

- **`name`**: snake_case identifier, unique within the source's MCP server.
- **`description`**: two to four sentences answering: what does this tool return, when should it be called, and what does it explicitly not cover. The description is injected into the LLM's context (see ADR-004) and must be sufficient for routing decisions without additional context.
- **`inputSchema`**: JSON Schema (draft 7) with all required parameters marked. Input parameters are typed: `string`, `number`, `boolean`, or `array` of those types. Nested objects in inputs are not permitted — inputs must be flat or at most one level of nesting. Constraint: the LLM constructs tool call parameters from natural language. Flat inputs reduce hallucination surface and simplify validation.
- **Return**: a `WarRoomResponse` envelope (see below). All tools return the same envelope shape; only the `data` field varies by tool.

Rejected alternative — tool-specific response shapes: war-room would need source-specific parsing logic for each tool. The uniform envelope means the orchestrator can handle all responses identically up to the `data` field, and coverage and error processing is shared across all sources.

---

### WarRoomResponse envelope

**Decision**: every tool must return exactly this structure:

```json
{
  "data": "<tool-specific content, or null if error>",
  "coverage": {
    "requested": "<echo of the input parameters relevant to scope>",
    "covered": "<what was actually returned, same shape as requested>",
    "is_complete": "<boolean>",
    "gaps": ["<human-readable description of gap 1>"],
    "freshness_at": "<ISO 8601 timestamp of most recent data point, or null>"
  },
  "error": null
}
```

Or, on failure:

```json
{
  "data": null,
  "coverage": {
    "requested": "<echo of input, or null if request could not be parsed>",
    "covered": null,
    "is_complete": false,
    "gaps": [],
    "freshness_at": null
  },
  "error": {
    "code": "<standard error code>",
    "message": "<human-readable explanation>",
    "retryable": "<boolean>"
  }
}
```

**Mutual exclusivity**: `data` is non-null when the call succeeded (even partially). `error` is non-null when the call failed. These are mutually exclusive: never both non-null; never both null.

**`coverage` is always present**, even when `error` is non-null. When a hard failure occurs (`SOURCE_UNAVAILABLE`), `covered` and `gaps` may be null or empty — but the `coverage` object itself must be present so the orchestrator can process all responses with the same code path.

Rejected alternative — omit coverage on error: the orchestrator would need conditional coverage handling. The uniform structure is cleaner.

Rejected alternative — flatten coverage fields into the top-level envelope: fields like `is_complete` and `gaps` would collide with tool-specific response fields. The nested `coverage` object gives unambiguous namespacing.

---

### Coverage metadata semantics

**Decision**: the `coverage` fields have the following semantics:

**`requested`**: an echo of the scope-relevant input parameters. For time-range queries, this is the requested time window. For metric queries, this includes the metric name and window. The exact shape mirrors the corresponding input parameters — not a free-form field — so the orchestrator can programmatically compare `requested` against `covered`.

**`covered`**: the scope actually returned. Same shape as `requested`. If a tool was asked for `{"from": "2026-04-01", "to": "2026-04-15"}` and only has data from April 3rd, `covered` is `{"from": "2026-04-03", "to": "2026-04-15"}`. The LLM sees the difference without needing source-specific logic.

**`is_complete`**: `true` if `covered` equals `requested` with no gaps. `false` if any requested scope was not returned. This is the fast-path check: if `is_complete: true`, the Case B prompt path in ADR-002 is not triggered.

**`gaps`**: a list of human-readable strings describing specific gaps within the covered scope. Written as factual statements the LLM can cite verbatim when explaining limitations to the PM: `"No scan data available for mx_android from 2026-04-20 to 2026-04-22 due to sync failure"`. Not error codes. Not internal references. Strings a PM can read. May be empty even when `is_complete: false`, if the source cannot enumerate specific gaps — in which case `is_complete: false` alone triggers the Case B behavior.

**`freshness_at`**: ISO 8601 timestamp of the most recent data point in the response. Null when not applicable (e.g., static reference data). Enables war-room to warn the PM when data is stale.

This coverage structure enables the exact Case B behavior defined in ADR-001 Section 4f: war-room can distinguish "I have complete data" from "I have partial data, here is what's missing and why", with the explanation coming from the source, not from war-room fabricating it.

Rejected alternative — boolean `is_complete` only, no `gaps`: war-room could only say "some data was missing", not why. ADR-001 Section 4f Case B requires the explanation, not just the flag.

Rejected alternative — `gaps` as structured objects (range type, missing dimension, reason code): richer but forces sources to classify gaps in a taxonomy war-room doesn't yet need. Human-readable strings are sufficient for the MVP and can be structured in a future ADR if querying gap reasons programmatically becomes necessary.

---

### Standard error codes

**Decision**: all war-room sources use the following shared error vocabulary:

| Code | Meaning | `retryable` |
|------|---------|------------|
| `SOURCE_UNAVAILABLE` | MCP server unreachable or returning 5xx | `true` |
| `AUTH_FAILURE` | Authentication or authorization failed | `false` |
| `INVALID_PARAMS` | Tool called with missing or malformed parameters | `false` |
| `DATA_NOT_FOUND` | Valid request, but no data exists for the given scope | `false` |
| `PARTIAL_FAILURE` | Tool completed but returned significantly less data than requested | `false` |
| `RATE_LIMITED` | Source is enforcing rate limits on this client | `true` |

Sources may define additional codes for source-specific conditions. Additional codes must not reuse the names above. War-room treats any unknown code as equivalent to `SOURCE_UNAVAILABLE` unless the response explicitly sets `retryable: false`.

The `retryable` field drives ADR-002's retry logic: `true` → one automatic retry; `false` → passed to the loop immediately as a failure.

Rejected alternative — HTTP status codes only, no semantic vocabulary: status codes are transport-level. 404 from pulse when a metric has no data is semantically different from 404 when the route doesn't exist. The semantic codes carry the distinction.

Rejected alternative — rich error taxonomy with categories and subcategories: over-engineering for the current set of sources. The six codes above cover every realistic failure mode at MVP. Extend through ADR supersession when a concrete gap emerges.

---

### Contract evolution

**Decision**: the MCP contract evolves through ADR supersession (Atlas Principle 10). There is no `contract_version` field in the WarRoomResponse envelope.

When the contract changes incompatibly, a new ADR supersedes this one. Concrete source specifications (Phase 1a.4) reference this ADR and are updated in the same ADR cycle as any incompatible contract change.

Rejected alternative — version field in envelope: consistent with Atlas `working-with-llms.md` Bias #4. Adds the implicit promise of backward compatibility without external consumers who require it. The Atlas ecosystem is a single team; coordinate version bumps through ADRs, not through runtime version negotiation.

---

## Consequences

**Positive**
- The uniform envelope means the orchestrator has one code path for all responses. Coverage checking, error handling, and Case B prompting are shared, not per-source.
- Human-readable `gaps` strings can be cited verbatim by the LLM when explaining limitations to the PM — no translation layer.
- The flat input parameter constraint reduces the surface area for LLM-driven tool call hallucinations.

**Negative / trade-offs**
- Sources must implement the coverage metadata faithfully for Case B honesty to work. A source that always returns `is_complete: true` trivially satisfies the contract but breaks the honesty guarantee. There is no automated check for good-faith coverage reporting; this is a trust assumption on source implementations.
- The `requested` / `covered` same-shape requirement may be awkward for sources with non-range scopes (e.g., a tool that returns data for a fixed set of platforms). Source authors must define a sensible `requested` → `covered` mapping for their tool's specific semantics.
- Contract changes are coordinated through ADR supersession across sessions — a pulse or release-agent implementation that deploys an incompatible change without a corresponding war-room ADR update will cause tool errors at runtime. There is no automatic compatibility negotiation; human coordination across sessions is the only safeguard.

**Constraints introduced**
- All war-room sources must return the WarRoomResponse envelope. A source that returns tool-specific JSON outside this envelope is non-conforming and will cause orchestrator errors.
- Error codes added by sources must not reuse the six standard codes. Namespace conflicts break the orchestrator's error routing.
- `data` and `error` are mutually exclusive. Sources that return partial success with an error in the same response must use `PARTIAL_FAILURE` with `is_complete: false` and gaps — not both fields populated.

---

## Related decisions

- ADR-001 Section 4d — MCP as the exclusive integration protocol
- ADR-001 Section 4f Case B — the honesty case that coverage metadata enables
- ADR-002 — loop behavior that consumes WarRoomResponse and acts on Cases A/B
- ADR-004 — tool descriptions that complement the tool signatures defined here
