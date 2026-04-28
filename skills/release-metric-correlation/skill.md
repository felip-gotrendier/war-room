# Skill: release-metric-correlation

Retrieves releases from release-agent for a time window and identifies
which releases temporally overlap with a metric deviation.

## Purpose

Given a time window — typically derived from a metric finding — retrieve
the release history and identify candidate releases: those whose deploy
time overlaps with the onset or progression of a metric deviation. This
skill produces a list of candidate releases with temporal correlation
reasoning, not a causal conclusion.

## When to invoke

- After `funnel-investigation` has identified a metric deviation with an
  onset date, to look for releases that coincide.
- When the PM's question explicitly mentions a time period and asks what
  was released ("what went out since April 15?").
- When source-routing identifies release-agent as relevant after a metric
  finding is already in context.

## Inputs

Required:
- Time window (start date, end date). Typically the metric deviation window
  from a prior `funnel-investigation` finding.

Optional:
- Repository filter (e.g., `android`, `backend`). If absent, query all
  repositories tracked by release-agent.
- Metric finding from context (onset date, affected platforms) — used to
  narrow relevance assessment.

## Process

1. Call `get_releases(repo, date_range)` for the specified window. If no
   repository filter, call for each repository in
   `knowledge/sources/release-agent.md`'s repository list.
2. For each release returned:
   a. Note the deploy timestamp and repository.
   b. If a metric onset date is in context: assess temporal proximity.
      A release deployed within 24 hours before metric onset is a strong
      candidate. A release deployed 3–7 days before is a weak candidate.
      A release deployed after metric onset cannot be causal — note this
      and do not include it as a candidate.
   c. Call `explain_release(repo, id)` for strong and weak candidates to
      get the narrative of what changed.
3. Classify candidates:
   - **Strong**: deployed within 24h before metric onset.
   - **Weak**: deployed 1–7 days before metric onset, or deployed globally
     when the metric drop is platform-specific (lower prior, per
     `knowledge/repo-platform-mapping.md`).
   - **Coincidental**: deployed around the same time but in repositories
     confirmed unrelated to the affected metric's platform, per the
     repo-platform mapping.
4. Report all candidates with their classification. Do not discard weak
   candidates — the PM may have context that raises or lowers their prior.

## Outputs

A structured finding:

```
Time window: [start] to [end]
Repositories queried: [list]
Coverage: [complete | partial — describe gap]

Candidate releases:
- [repo] [release-id] ([timestamp]) — [classification: strong/weak/coincidental]
  What changed: [summary from explain_release]
  Temporal reasoning: [why this is classified as it is]

Releases with no temporal overlap: [count] releases outside the relevant
window; not listed unless the PM requests them.
```

If no releases were deployed in the window: state this clearly.

## Dependencies

MCP tools:
- `release-agent.get_releases(repo, date_range)` — release list for a
  repository and time window.
- `release-agent.explain_release(repo, id)` — narrative of what a specific
  release changed.

Knowledge base:
- `knowledge/sources/release-agent.md` — repository list and tool
  descriptions.
- `knowledge/repo-platform-mapping.md` (to be defined in Phase 1a.3) —
  which repositories affect which platforms; used to classify releases as
  coincidental when the metric drop is platform-specific.

## Limitations

- Produces temporal correlation, not causation. A release that coincides
  with a metric drop is a candidate, not a confirmed cause.
- Cannot access code diffs or file-level changes beyond what
  `explain_release` provides. Deep code analysis is not in scope.
- Does not assess whether a release is likely to affect a specific metric
  without `explain_release` data — do not speculate on platform impact
  from the release name or ID alone.
- When an MCP tool returns a failure response (Case A), the skill includes
  a "no data available" finding for the affected scope; orchestrator
  behavior downstream is per ADR-002.
