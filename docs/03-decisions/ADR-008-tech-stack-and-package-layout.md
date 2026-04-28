# ADR-008: Tech stack and package layout

**Status:** Accepted
**Date:** 2026-04-28
**Project:** war-room (Atlas Layer 3)

---

## Context

War-room is the first tool in the Atlas ecosystem built as a pure MCP client:
it calls pulse and release-agent via MCP, but exposes no MCP server of its own.
This role shapes its package layout differently from pulse (server + scheduler)
and release-agent (server + webhook). This ADR defines the Python package
structure, dependency choices, and where war-room follows ecosystem conventions
versus where its client role justifies divergence.

---

## Decisions

### Python version and runtime

**Decision**: Python ≥ 3.11. Consistent with pulse and release-agent. No lower
bound is justified by any war-room-specific requirement.

---

### Package layout: `war_room/` + `api/` split

**Decision**: the Python package is split into two top-level directories:

```
war_room/              # business logic — no HTTP imports
  __init__.py
  orchestrator.py
  models.py
  knowledge_loader.py
  clients/
    __init__.py
    pulse_client.py
    release_agent_client.py
  skills/
    __init__.py
    source_routing.py
    funnel_investigation.py
    release_metric_correlation.py
    hypothesis_formation.py
    investigation_summary.py
api/                   # HTTP layer — FastAPI, routes, Pydantic models
  __init__.py
  main.py
  routes.py
  models.py
```

`war_room/` has no FastAPI or HTTP imports. It can be imported and tested
without an HTTP context. The orchestrator, clients, and skills are pure async
Python.

`api/` imports `war_room/` and adds the HTTP surface. FastAPI app creation,
lifespan, and route handlers live here.

This follows release-agent's `agent/` + `api/` separation rather than pulse's
single-package structure. The reason: pulse is simultaneously a server, a
scheduler, and a Slack bot — a single-package structure is coherent there.
War-room's core is an orchestrator + MCP clients; the HTTP layer is thin.
Separation keeps the orchestrator testable without HTTP scaffolding.

The Python module name is `war_room` (underscore), not `war-room` (hyphen),
following Python module naming convention. The project name remains `war-room`.

---

### Skill prompts at `skills/<name>/prompts/`

**Decision**: all Claude prompt content lives in markdown files under
`skills/<name>/prompts/`. No prompt strings appear in any `.py` file.

This adopts pulse ADR-013 without modification. The root `skills/<name>/`
directory already contains `skill.md` (the spec). Prompts extend it as a
sibling subdirectory. At runtime, `war_room/skills/<name>.py` reads its
prompt files; the prompt content is data, not code.

The root `skills/<name>/` directory serves three roles: spec (`skill.md`),
Claude prompts (`prompts/`), and the Python implementation lives in
`war_room/skills/<name>.py`. The separation between root `skills/` (data)
and `war_room/skills/` (code) mirrors pulse's `./skills/` vs
`./pulse/skills/` structure.

---

### No MCP server

**Decision**: war-room exposes no MCP server endpoint. The `mcp` package is
included for its client capabilities only. War-room is a pure MCP consumer.

This is the defining structural difference from pulse and release-agent.
`api/main.py` mounts no `/mcp` sub-app. The `mcp` dependency provides
`streamablehttp_client` and `ClientSession` (ADR-009); nothing else from
the server side of the SDK is used.

---

### Dependencies

```toml
[project]
name = "war-room"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "mcp>=1.27.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
]
```

Version floors take the maximum requirement between pulse and release-agent
for shared dependencies. `mcp>=1.27.0` follows release-agent (the more recent
of the two). `pytest-httpx` is excluded; `respx` is sufficient for HTTP
mocking in tests.

Excluded intentionally: `slack-bolt` (Phase 2b), `apscheduler` (no background
jobs in Phase 2a), `pandas` (no CSV processing), `gspread` (no Google Sheets).

---

## Consequences

**Positive**
- `war_room/` is independently testable without HTTP context.
- No prompt content in Python source files; prompts are editable without
  touching code.
- Consistent version floors with the ecosystem.

**Negative / trade-offs**
- Two-directory layout adds a level of indirection compared to a single
  package. Justified by the separation of concerns; reconsidered only if
  war-room grows a scheduler or server component.

**Constraints introduced**
- No FastAPI or HTTP imports may appear in `war_room/`. Only `api/` may
  import FastAPI.
- No Claude prompt content in any `.py` file (pulse ADR-013 constraint,
  adopted here).
- `war_room/knowledge_loader.py` is the sole entry point to `knowledge/`.
  Direct file reads from other modules are a violation (ADR-011).

---

## Related decisions

- ADR-001 — vision: war-room as Layer 3, web interface, MCP consumer
- ADR-009 — MCP client design (uses `mcp>=1.27.0` for client transport)
- ADR-010 — orchestrator uses `war_room/` package layout
- ADR-011 — protected elements include API endpoint paths and knowledge
  loader entry point
