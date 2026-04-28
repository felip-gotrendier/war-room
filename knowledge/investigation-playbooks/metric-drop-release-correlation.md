# Metric drop correlated with a recent release

## Symptoms

The PM observes a decline in one or more funnel metrics (active users at a
funnel stage, or a conversion rate between stages) and wants to know whether
a recent release caused it.

## Trigger conditions

Use this playbook when:
- A specific metric or funnel stage is named or implied.
- The time window is recent enough that release-agent coverage is plausible
  (within the last 30 days).
- The question is "what caused this drop?" not "is there a drop?" (if the
  latter, start with `funnel-investigation` without this playbook).

Do not use this playbook when:
- The PM describes an infrastructure symptom (latency, errors) — route to
  Datadog instead (not yet connected at MVP).
- The PM asks about a metric that is not a funnel stage — gap-declare if
  pulse does not cover it.

## Investigation sequence

1. **funnel-investigation**: query pulse for the named metric and window.
   Characterize the deviation: onset date, magnitude, affected platforms.
   — If no deviation: stop and report. Do not proceed to release correlation.

2. **release-metric-correlation**: query release-agent for the window
   [onset_date − 7 days, onset_date + 1 day]. This range catches releases
   deployed up to 7 days before onset (weak candidates) and the day of onset
   (strong candidates).
   — Steps 1 and 2 can be run in parallel if the PM's question implies both
     a metric and a time period.

3. **hypothesis-formation**: synthesize the metric finding and the release
   candidates into a structured hypothesis.

4. (If confidence is Working or Speculative): query `explain_release` for
   remaining candidates to assess mechanistic plausibility. Re-run
   hypothesis-formation with the new data.

## Hypotheses to test

**H1 — Mobile app release caused the drop**
- Confirming: a mobile release deployed within 24h before onset; the drop is
  platform-specific to the released platform; `explain_release` describes
  changes to the affected funnel stage's UI or flow.
- Refuting: the drop is cross-platform (all platforms drop simultaneously,
  including web); no mobile release in the window; `explain_release` shows
  no changes relevant to the affected stage.

**H2 — Backend release caused the drop**
- Confirming: a backend release deployed within 24h before onset; the drop
  is simultaneous across all platforms; `explain_release` describes changes
  to APIs used by the affected funnel stage.
- Refuting: the drop is platform-specific (only one mobile platform); no
  backend release in the window.

**H3 — External event (not a release)**
- Confirming: no releases in the 7-day window before onset; the drop is
  single-country (mx only or co only); the onset coincides with a known
  external event (holiday, payment provider incident).
- Refuting: releases exist in the window with plausible mechanistic paths;
  the drop is cross-country.

**H4 — Data pipeline artifact**
- Confirming: the drop is a single-day spike followed by recovery to baseline;
  `check_metric` returns `is_complete: false` or low freshness; the drop
  appears simultaneously across all platforms and all funnel stages.
- Refuting: the drop persists across multiple days; only one funnel stage is
  affected.

## Known false positives

- **Holiday traffic shift**: a drop in absolute active users on a regional
  holiday is not a regression — conversion rates remain stable even if volume
  drops. Check conversion rates, not just absolute counts.
- **Gradual trend misread as drop**: a metric declining over 2–3 weeks may
  have no single-release cause. Require an onset date with a meaningful step
  change before correlating with a release.
- **Coincidental release timing**: a release deployed 5 days before onset in
  an unrelated repository (e.g., notisfier release when the drop is in
  checkout on web) is coincidental. Use `knowledge/repo-platform-mapping.md`
  to assess relevance.

## Confirming evidence

The investigation can close with High confidence when:
- A release is identified with strong temporal overlap (≤24h before onset).
- `explain_release` describes a change with a clear mechanistic path to the
  affected metric.
- The platform distribution of the drop matches the platform scope of the
  release.
- No significant contrary evidence is present.

If all three conditions are met but one is only partially supported, close
with Working confidence and name what would resolve the remaining uncertainty.
