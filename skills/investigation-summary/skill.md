# Skill: investigation-summary

Synthesizes all conversation findings and the final hypothesis into a
structured investigation document suitable for sharing and publishing.

## Purpose

Given the accumulated context of a completed investigation — the original PM
question, findings from `funnel-investigation` and `release-metric-correlation`,
and the final hypothesis from `hypothesis-formation` — produce a single
markdown document following the format defined in ADR-006. This skill renders
the investigation as a human-facing artifact; it does not perform reasoning or
call sources.

## When to invoke

- When the PM explicitly requests a document during or at the end of an
  investigation ("summarize this", "write this up", "give me a document").
- When the PM initiates a publish and no document has been generated in the
  current conversation. The orchestrator triggers this skill automatically
  before committing the publish.
- Not called mid-investigation for any other reason. `hypothesis-formation`
  handles the reasoning loop; `investigation-summary` handles synthesis for
  output only.

## Inputs

Required:
- Final hypothesis from `hypothesis-formation` (must be in context). If no
  hypothesis is in context, this skill cannot produce a complete document —
  see Limitations.
- At least one finding from `funnel-investigation` (metric findings).
- Original PM question (first user message of the investigation).

Optional:
- Findings from `release-metric-correlation` (included if in context; noted
  as "not queried" if absent).
- PM-provided title (passed explicitly if the PM names the document before
  requesting it).

## Process

1. Extract the original PM question from the start of the conversation.
2. Generate title:
   - If the PM provided a title: use it verbatim.
   - Otherwise: identify the primary metric name from the funnel-investigation
     findings and format as `<metric_name> investigation — <YYYY-MM-DD>`.
   - If no metric name is identifiable: use `Investigation — <YYYY-MM-DD>`.
3. Write the "Investigation" paragraph: name the sources queried (derived
   from which finding types are in context), count the metrics investigated,
   count the release candidates assessed if release-metric-correlation was
   invoked, and note the iteration count from conversation context.
4. Write the "Metric findings" subsection: transcribe each
   funnel-investigation finding from context in the order it was produced,
   preserving the structured finding format (Metric, Window, Coverage,
   Findings per platform, Summary).
5. Write the "Release candidates" subsection: transcribe the
   release-metric-correlation finding if in context, preserving its
   structured format. If release-metric-correlation was not invoked, write:
   "Not queried in this investigation."
6. Write the "Hypothesis" section: transcribe the final hypothesis-formation
   output verbatim, preserving all fields (Hypothesis, Confidence, Evidence
   for, Evidence against, What would confirm this, What would refute this).
7. Write the "Open questions" section: extract items from the hypothesis's
   "Next steps" and "What would confirm/refute this" fields; reformat as a
   bulleted list; remove duplicates between the two source fields.
8. Assemble into the full document following the section order in ADR-006.

## Outputs

A markdown string following the ADR-006 document format:

```
# <title>

**Question**: <original PM question, verbatim>

## Investigation
<one paragraph>

## Findings

### Metric findings
<structured findings blocks>

### Release candidates
<structured findings block, or "Not queried in this investigation.">

## Hypothesis
<final hypothesis-formation output, verbatim>

## Open questions
- <item>
- ...
```

Returned to the orchestrator for display in the UI and, when publishing,
for storage in `saved_investigations.document` (ADR-005).

## Dependencies

No MCP tools called. Reads only findings and hypothesis already in context.

ADR reference:
- ADR-006 — the document format this skill implements.

## Limitations

- Cannot produce a complete document without a final hypothesis in context.
  If called without a hypothesis, returns: "No hypothesis has been formed in
  this investigation. Run the investigation further before generating a
  document." The orchestrator must not trigger this skill if
  `hypothesis-formation` has not been invoked.
- Does not generate new insights. Sparse findings produce a sparse document.
- The "Open questions" section is derived mechanically from the hypothesis's
  existing fields. If "Next steps" is empty in the hypothesis, the section
  will be empty.
- Invoked once per conversation in the normal flow. If the PM requests a
  second document after further investigation (e.g., before republishing),
  the new document replaces the in-context one. The previous document
  persists in `saved_investigations` only if it was already published.
