# Skill: funnel-investigation

Retrieves funnel metric data from pulse and characterizes any deviation:
when it started, how large it is, and which platforms are affected.

## Purpose

Given a metric name and a suspected time window, query pulse for metric
data, identify whether a meaningful deviation exists, quantify it, and
describe its characteristics (onset date, magnitude, platform distribution).
This skill produces findings — structured observations about the data — not
hypotheses about causes.

## When to invoke

- When the PM's question references a specific metric or funnel stage.
- When source-routing identifies pulse as relevant to the current question.
- When a prior investigation step has produced a candidate time window that
  warrants a more detailed metric look.
- When the PM redirects to a specific platform or metric dimension ("check
  mx_android specifically", "what does the product_view stage show?").

## Inputs

Required:
- Metric name (e.g., `users_product_list/active`, `users_checkout/active`).
- Time window (start date, end date or relative window such as "last 14 days").

Optional:
- Platform filter (e.g., `mx_android`). If absent, query all platforms.
- Context from prior session findings (to avoid re-querying already-covered
  ground).

## Process

1. Call `check_metric(name, window)` for the requested metric and window.
   If a platform filter is specified, call once per platform. If not, call
   for each platform in `knowledge/sources/pulse.md`'s platform list.
2. If `is_complete: false` in any response, note the gaps explicitly — do
   not ignore them or treat partial data as complete.
3. For each platform response with complete or partial data:
   a. Identify whether the metric deviates meaningfully from its typical
      range. Use the benchmark context in `knowledge/metrics/` if available.
   b. If a deviation exists: identify its onset (the earliest date the
      metric falls outside normal range), quantify its magnitude (percentage
      change from the rolling baseline), and note its current trajectory
      (recovering, stable, worsening).
4. Summarize findings across platforms: is the deviation global (all
   platforms), regional (one country), or platform-specific (one app)?
5. If the requested metric shows no deviation, state this clearly — do not
   search for adjacent metrics to fill the expectation that "something must
   be wrong".

## Outputs

A structured finding, one per metric investigated:

```
Metric: [name]
Window: [start] to [end]
Coverage: [complete | partial — describe gap]

Findings:
- [platform]: [deviation description with onset date and magnitude, or
  "within normal range"]
- [platform]: ...

Summary: [one sentence characterizing the cross-platform picture]
```

## Dependencies

MCP tools:
- `pulse.check_metric(name, window)` — metric data for a specific metric
  and time window.
- `pulse.get_recent_anomalies(window)` — optionally used to cross-check
  whether pulse's automated detection already flagged this metric.

Knowledge base:
- `knowledge/sources/pulse.md` — platform list and tool descriptions.
- `knowledge/metrics/` — metric definitions and benchmark context
  (populated in Phase 1a.3; used when available).

## Limitations

- Produces observations about metric behavior, not causal explanations.
  Connecting a metric drop to a release is `release-metric-correlation`'s
  responsibility.
- Does not interpret anomalies beyond the funnel scope. Infrastructure-
  linked drops (Datadog) or user feedback signals (support-digester) are
  outside this skill's scope.
- Cannot fill in data gaps — if pulse has no data for a platform and window,
  this skill reports the gap; it does not approximate.
- When an MCP tool returns a failure response (Case A), the skill includes
  a "no data available" finding for the affected scope; orchestrator
  behavior downstream is per ADR-002.
