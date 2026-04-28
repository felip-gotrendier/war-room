# ADR-002: Iteration loop design

**Status:** Accepted
**Date:** 2026-04-27
**Project:** war-room (Atlas Layer 3)

---

## Context

ADR-001 (Section 4c) established that war-room reasons through multi-step iterative tool use: the LLM decides what source to consult, receives the result, and continues until it has enough to respond or a termination condition is met. This ADR defines the mechanics of that loop — how iterations are counted, when the loop stops, how failures are handled, and what state persists between steps.

---

## Decisions

### What constitutes an iteration

**Decision**: one iteration = one LLM API call, regardless of how many tool calls that LLM response requests.

Within a single iteration, the LLM may request zero tool calls (final response — normal termination), one tool call, or multiple tool calls (executed before the next iteration begins). All tool call results from an iteration are appended to the conversation context before the next LLM call.

This definition has a direct consequence for the iteration counter: requesting four tool calls in one LLM response costs one iteration, not four. This incentivizes the LLM to parallelize independent queries rather than sequence them artificially.

Rejected alternative — one iteration per tool call: granular counting prevents multi-tool parallelism within a single reasoning step. A complex investigation requiring both metric data and release history for the same time window would need two iterations instead of one, even though both queries are independent. The goal of the counter is to bound total reasoning steps, not total tool calls.

---

### Maximum iterations

**Decision**: the iteration cap is **15**. When the cap is reached, the loop does not terminate abruptly — the LLM receives one additional prompt: *"You have reached the maximum investigation steps. Summarize the findings so far, identify what remains uncertain, and describe what additional queries would have helped resolve it."* The LLM's response to this prompt is the final output.

Justification for 15:

- A typical investigation (routing → metric query → release query → hypothesis formation): 4–6 iterations.
- A complex investigation with one PM redirect and follow-up drill: 8–12 iterations.
- 15 provides a buffer above the expected maximum while remaining a meaningful bound on cost and latency.

The cap is deliberately conservative. If 15 proves insufficient for real GoTrendier investigations, an ADR revision increases it with justification from observed usage. The default errs toward early termination rather than uncapped execution.

**Counter behavior on PM redirect**: the counter does not reset when the PM sends a new message mid-investigation. The cap of 15 applies to the entire investigation session, not to individual directions within it. If a redirect arrives when fewer than 5 iterations remain, the LLM is informed: *"Note: fewer than 5 investigation steps remain in this session."* The threshold of 5 reflects the minimum for a meaningful follow-up: one iteration to understand the new direction, two to three queries against relevant sources, and one synthesis step. Below this threshold, the LLM cannot pursue a redirect substantively and the warning sets appropriate expectations.

Rejected alternative — reset counter on redirect: opens the possibility of very long sessions through repeated redirections (15 iterations × N redirects). The per-session cap is the correct constraint.

Rejected alternative — separate caps per direction: adds bookkeeping complexity without clear benefit. The session cap is simpler and sufficient.

---

### Normal termination

**Decision**: the loop terminates normally when the LLM returns a response with no tool calls. This is the primary termination path — the LLM has decided it has enough information to respond.

No special signal is required from the LLM. The absence of tool calls in the response is the signal.

---

### Tool failure handling

Tool failures within the loop connect directly to ADR-001 Section 4f (Cases A, B, C). The loop's behavior differs by case:

**Case A — tool unreachable** (MCP call fails at transport or protocol level):
The failure and its error code (from ADR-003) are appended to the context as a tool result. The LLM sees the failure and decides the next step: proceed with remaining sources, explain the gap to the PM, or — if no productive path remains — produce a summary with the gap noted. The orchestrator does not halt the loop on a single tool failure.

Exception: if the same tool fails on two consecutive iterations (identified by tool name and parameter hash), the orchestrator adds a system message before the next LLM call: *"[tool_name] has failed twice in succession and should not be called again in this session."* This prevents the LLM from looping on a broken source.

**Case B — partial data** (tool responds with `is_complete: false` in coverage metadata):
The data and the coverage metadata are both appended to the context. The LLM sees what was returned and what was missing, including any human-readable gap descriptions from the `gaps` field. The loop continues — partial data is not a failure condition.

**Case C — tool not in connected sources**:
Handled before the LLM API call, not during it. See ADR-004 for the dual-layer rejection mechanism. Case C does not enter the loop.

Rejected alternative — halt loop on any single tool failure: defeats the purpose of a multi-source investigation. If pulse is unavailable, war-room should still be able to interrogate release-agent and produce a partial result.

Rejected alternative — automatic retry within the loop on failure: retry logic is handled at the MCP call layer (see below). By the time a failure reaches the loop, retries are exhausted. The loop does not re-invoke the retry layer.

---

### Retry logic

**Decision**: each MCP tool call gets at most one automatic retry, applied at the MCP client layer before the result (success or failure) is passed to the loop.

- **Transient errors** (`retryable: true` in the error response, per ADR-003): one retry after a 2-second delay. If the retry fails, the failure is passed to the loop as Case A.
- **Definitive errors** (`retryable: false`): no retry. The error is passed to the loop immediately.
- **Timeout**: treated as a transient error; one retry.

The retry is transparent to the loop — the loop always receives either a successful result or a final failure, never a retry-in-progress state.

Rejected alternative — multiple retries: adds latency proportional to the retry count. If a source is down, a second attempt 4 seconds later is unlikely to succeed where a first retry at 2 seconds did not. One retry catches brief network glitches; more retries catch outages that will resolve on their own — and for those, the user should be informed, not silently delayed.

---

### State between iterations

**Decision**: the full conversation context (the messages array, including all LLM responses, tool calls, and tool results) is passed to each LLM API call. No selective pruning between iterations during normal operation.

If the context approaches the model's context window limit (estimated by token count), the orchestrator summarizes earlier tool results before the next LLM call. The summarization logic is deferred to the implementation ADR — this is a defensive mechanism, not a normal path for investigations within the expected iteration count.

Rejected alternative — pass only the latest iteration's context: loses the thread of the investigation. The LLM cannot form a coherent hypothesis without seeing how earlier queries led to the current state.

---

## Consequences

**Positive**
- The 15-iteration cap with a hard-stop summary ensures every investigation produces a usable output, even if it runs long.
- Parallel tool calls within one iteration allow the LLM to optimize for latency when queries are independent — a common case in metric + release investigations.
- The failure handling connects cleanly to ADR-001's three honesty cases without requiring special-casing in the loop.

**Negative / trade-offs**
- A session with many PM redirects may exhaust its cap before completing a final direction. The "fewer than 5 iterations remain" warning mitigates this but does not eliminate it.
- The repeated-failure detection (same tool, two consecutive iterations) relies on parameter hashing, which requires an implementation decision about what constitutes "the same" call.

**Constraints introduced**
- The orchestrator must maintain a tool-call failure registry per session to implement the "same tool fails twice" detection.
- The orchestrator must estimate context size to implement the defensive summarization fallback. The token estimation strategy is deferred to the implementation ADR.
- The counter does not reset on PM redirect. If a future investigation pattern reveals this is too restrictive, an ADR revision is required.

---

## Related decisions

- ADR-001 Section 4c — multi-step iterative tool use as the reasoning model
- ADR-001 Section 4f — Cases A, B, C: the honesty cases that tool failure handling implements
- ADR-003 — WarRoomResponse envelope and error codes that the loop receives from tool calls
- ADR-004 — source routing and Case C rejection, which operates before the loop
