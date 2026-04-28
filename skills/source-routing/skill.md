# Skill: source-routing

Translates a PM's natural language question into an ordered set of source
queries, and identifies when no connected source can answer the question.

## Purpose

Given a PM's question — at the start of an investigation or after a
mid-session redirect — determine which connected sources are relevant,
in what order to query them, and what parameters to use for the initial
queries. When no connected source covers the question, produce an explicit
gap declaration rather than approximating.

This skill runs at the beginning of every investigation and after every PM
redirect. It does not query sources itself; it produces a query plan that
the orchestrator executes.

## When to invoke

- At session start, when the PM's first message has been received.
- When the PM redirects mid-investigation ("did you check X?", "focus on
  platform Y", "what about the period before that?").
- When the current investigation branch has exhausted its findings and the
  orchestrator needs to decide what to explore next.

## Inputs

Required in context:
- The PM's question or redirect (verbatim).
- The list of connected sources and their descriptions (injected into system
  prompt from `knowledge/sources/` per ADR-004).

Optional in context (present when invoked after the first iteration):
- Findings from previous skills in this session, summarized.
- Any sources already queried and their coverage results.

## Process

1. Read the connected sources section of the system prompt.
2. Identify which sources are relevant to the PM's question. A source is
   relevant if its scope covers at least one aspect of the question.
3. For each relevant source, identify which tools to call and with what
   parameters. Prefer specific, narrow queries over broad ones — a query
   for `users_product_list/active` over the last 14 days is better than a
   query for "all metrics" over the last 30 days.
4. Order sources by expected relevance to the question. The source most
   likely to produce the first useful finding goes first.
5. When two or more sources are relevant and their queries are independent
   (neither result changes whether the other query is worth making), mark
   them as parallelizable.
6. If no connected source covers the question, produce a gap declaration:
   name what would be needed, state that it is not connected, and stop.
   Do not approximate from available sources.

## Outputs

One of two outputs:

**Query plan** (when at least one source is relevant):
```
Sources to query (in order):
1. [source name] — [tool name]([parameters]) — [one-line rationale]
2. [source name] — [tool name]([parameters]) — [one-line rationale]
   [mark as parallelizable with #1 if independent]
```

**Gap declaration** (when no source is relevant):
```
The question requires [description of needed data], which is not available
from any connected source. Connected sources cover: [brief list].
To investigate this, [source name] would need to be connected.
```

## Dependencies

- `knowledge/sources/*.md` — connected source descriptions (read via system
  prompt injection; not read directly by this skill at runtime).
- No MCP tools are called by this skill.

## Limitations

- Does not query sources — produces a plan only. Execution is the
  orchestrator's responsibility.
- Cannot determine in advance whether a source will return complete data;
  coverage gaps emerge at query time (Case B).
- Does not decide termination — only decides what to query next. The
  orchestrator decides when the loop has enough to respond.
