# Knowledge base

This directory contains the business knowledge that war-room's orchestrator
and skills use at runtime. It is not documentation for human readers — it is
data that the LLM reads directly. Write entries accordingly: precise, without
hedging, second person where instructive.

## Structure

```
knowledge/
  sources/          — Connected MCP sources and their capabilities
  metrics/          — Funnel metric definitions and benchmark context
  investigation-playbooks/  — Anchored patterns for known incident types
  repo-platform-mapping.md  — Which repositories affect which platforms
```

## Editing guidelines

- Write for the LLM, not for the team. A reader in a code review is secondary.
- Use explicit negative guidance ("does NOT know", "do NOT query here for X").
  The LLM routes better with explicit anti-patterns than with scope descriptions alone.
- Do not add hedging language ("might", "could be useful"). State facts.
- When a file references a Phase 1a.3 stub, mark it clearly with
  `<!-- stub: validate in Phase 2 -->` so it is not mistaken for validated data.
- Keep entries current. A stale benchmark in `metrics/` is worse than no benchmark.

## Adding a new source

1. Implement its MCP server and register it in war-room's tool set.
2. Create `knowledge/sources/<name>.md` following the format in
   `knowledge/sources/README.md`.
3. All three steps are required. A source registered without a knowledge file
   is undescribed to the LLM. A knowledge file without a registered server
   causes the LLM to propose tool calls that will fail at dispatch.
