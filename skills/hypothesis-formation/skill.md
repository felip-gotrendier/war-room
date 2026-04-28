# Skill: hypothesis-formation

Synthesizes findings from prior skills into a structured hypothesis: a
claim about cause and effect, with explicit confidence framing and named
contrary evidence.

## Purpose

Given findings in context — metric characterizations, correlated releases,
any other evidence — produce a hypothesis that connects an observed effect
(a metric deviation) to a plausible cause (a release, an external event, a
data anomaly). The hypothesis is framed with explicit confidence level and
must name contrary evidence if any exists.

This skill can be invoked multiple times in a session. Each invocation
replaces the previous hypothesis — does not append to it. The first
invocation produces a provisional hypothesis that guides subsequent queries;
later invocations refine it as evidence accumulates.

## When to invoke

- After `funnel-investigation` and `release-metric-correlation` have
  produced findings sufficient to propose a first hypothesis.
- After the PM provides a redirect that adds new evidence or context.
- When the PM explicitly asks "what do you think is happening?".
- When the orchestrator has reached or is approaching the iteration cap
  and needs to produce a final synthesis.

## Inputs

Required:
- At least one finding from a prior skill (metric finding, release
  candidates, or both).

Optional:
- Prior hypothesis from an earlier invocation in this session (for
  refinement, not for preservation — it will be replaced).
- PM context provided in the conversation (observations, intuitions, known
  events not in connected sources).

## Process

1. Identify the observed effect: which metric, on which platforms, from
   when, of what magnitude.
2. Identify the most plausible cause from available evidence. A cause is
   plausible when:
   - It is temporally consistent (precedes the effect).
   - It has a mechanistic path (the code that changed could plausibly affect
     the metric).
   - It is consistent with the platform distribution of the effect (a
     backend release is a weaker candidate for a mobile-only drop than an
     Android release).
3. Assess confidence:
   - **High**: strong temporal overlap, mechanistic path is clear, no
     significant contrary evidence.
   - **Working**: some temporal overlap or plausible mechanism, but evidence
     is incomplete or partially inconsistent.
   - **Speculative**: temporal overlap is weak or mechanism is unclear;
     proposed as a direction for further investigation, not a conclusion.
4. Identify contrary evidence: findings that are inconsistent with the
   hypothesis. Name them explicitly — do not omit evidence that weakens
   the hypothesis. If contrary evidence is strong, lower the confidence
   level.
5. Identify what would confirm or refute the hypothesis: which source,
   query, or data point, if available, would resolve the remaining
   uncertainty.
6. If findings are insufficient to form any hypothesis above Speculative,
   state what is missing rather than producing a low-quality hypothesis.

## Outputs

A structured hypothesis:

```
Hypothesis: [one sentence — cause → effect]
Confidence: [High | Working | Speculative]

Evidence for:
- [finding supporting the hypothesis]

Evidence against:
- [contrary finding, if any; or "None identified"]

What would confirm this:
- [specific source, query, or data point that would resolve uncertainty]

What would refute this:
- [specific finding that would eliminate this hypothesis]

Next steps:
- [recommended follow-up queries or sources, if investigation continues]
```

## Dependencies

No MCP tools are called by this skill. It reasons over findings already
in context.

Knowledge base:
- `knowledge/metrics/` — metric definitions and known causal relationships
  (populated in Phase 1a.3; used when available).
- `knowledge/investigation-playbooks/` — anchored investigation patterns
  for known GoTrendier incident types (populated in Phase 1a.3).

## Limitations

- Cannot produce a High-confidence hypothesis without both a metric finding
  and a correlated release. If only one is available, confidence is Working
  at most.
- Does not access sources directly — reasons only over findings already
  in context. If evidence is missing, say so rather than speculating beyond
  the available data.
- When the PM provides intuition not backed by data ("I think it's the
  new checkout flow"), treat this as weak evidence to test, not as a finding
  to incorporate uncritically.
