# Metrics

This directory contains war-room's editorial summaries of GoTrendier funnel
metrics: their definitions, normal ranges, and known causal relationships.

**Source of truth**: metric definitions live in pulse's own knowledge base
(`pulse/knowledge/metrics/`). The files here are war-room's editorial summaries,
maintained in sync manually. Sync verification is a Phase 2 task — treat
entries here as provisional until that verification is complete.

## File format

```markdown
# <metric name or group>

## Definition
<what the metric measures, how it is computed>

## Platforms
<which platforms report this metric; note any platform-specific nuances>

## Normal range
<typical values or ranges per platform; mark as provisional if unvalidated>

## Known causal relationships
<what changes in product or releases are known to move this metric>

## Anomaly patterns
<what deviations look like when they are genuine vs. data artifacts>
```

## Adding a metric

Add a file or extend an existing file. Mark any benchmark that has not been
validated against real pulse data with `<!-- provisional: validate Phase 2 -->`.
Do not remove the provisional mark until the value has been confirmed.

## Currently documented

- `funnel-metrics.md` — funnel stages 0–4 across all platforms
