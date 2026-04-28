# ADR-011: Protected decisions

**Status:** Accepted — living registry
**Date:** 2026-04-28
**Project:** war-room (Atlas Layer 3)

---

## Context

Atlas Principle 9 defines protected decisions as decisions that silently break
downstream consumers if changed without coordination. Release-agent ADR-014
formalizes a registry of such elements. This ADR establishes war-room's
equivalent registry for Phase 2a.

A decision is PROTECTED if changing it without a new ADR and coordinated
updates breaks behavior in a way that is not caught by the test suite alone —
for example, a renaming that passes tests because tests mock the renamed
symbol, but breaks the actual LLM parsing or the MCP contract.

**This ADR is a living registry.** Unlike other ADRs in this project, it is
explicitly designated as mutable: new PROTECTED elements are registered by
amending this document with a dated entry. This is an exception to Atlas
Principle 10 (decisions are immutable once accepted) — the exception exists
because a growing registry that requires a new ADR per new element would
produce dozens of near-identical ADRs with no analytical content. Modifications
to an *existing* protected element still require a new ADR that describes the
change and why; only additions to the registry use the amendment path.

---

## Registry

### MCP tool names

| Tool name | Location(s) |
|-----------|-------------|
| `check_metric` | `war_room/clients/pulse_client.py`, `war_room/orchestrator.py` |
| `get_recent_anomalies` | `war_room/clients/pulse_client.py`, `war_room/orchestrator.py` |
| `trigger_scan` | `war_room/clients/pulse_client.py`, `war_room/orchestrator.py` |
| `get_releases` | `war_room/clients/release_agent_client.py`, `war_room/orchestrator.py` |
| `get_release` | `war_room/clients/release_agent_client.py`, `war_room/orchestrator.py` |
| `explain_release` | `war_room/clients/release_agent_client.py`, `war_room/orchestrator.py` |

**Why protected**: bilateral contract with pulse and release-agent (ADR-009).
Renaming requires coordinated change with upstream MCP servers. A rename that
passes war-room's tests still breaks at runtime against the real servers.

---

### Skill prompt section headers

| Skill | Protected headers | Location |
|-------|-------------------|----------|
| `funnel-investigation` | `Metric:`, `Window:`, `Coverage:`, `Findings:`, `Summary:` | `skills/funnel-investigation/prompts/investigate.md`, `war_room/skills/funnel_investigation.py` |
| `release-metric-correlation` | `Time window:`, `Repositories queried:`, `Coverage:`, `Candidate releases:` | `skills/release-metric-correlation/prompts/correlate.md`, `war_room/skills/release_metric_correlation.py` |
| `hypothesis-formation` | `Hypothesis:`, `Confidence:`, `Evidence for:`, `Evidence against:`, `What would confirm this:`, `What would refute this:`, `Next steps:` | `skills/hypothesis-formation/prompts/hypothesize.md`, `war_room/skills/hypothesis_formation.py` |
| `source-routing` | `Sources to query`, `The question requires` | `skills/source-routing/prompts/routing.md`, `war_room/skills/source_routing.py` |
| `investigation-summary` | `## Investigation`, `## Findings`, `## Hypothesis`, `## Open questions` | `skills/investigation-summary/prompts/summarize.md`, `war_room/skills/investigation_summary.py` |

**Why protected**: parsing contract between LLM prompt output and Python
parsers (ADR-010). Renaming a header in the prompt without updating the parser
produces a silent parse failure: Claude produces correct text but the parser
fails to extract the structured data.

---

### Internal data model schema

| Model | Location |
|-------|----------|
| `WarRoomFinding` | `war_room/models.py` |
| `ConversationContext` | `war_room/models.py` |
| `Coverage` (internal) | `war_room/models.py` |

**Why protected**: `WarRoomFinding` is consumed by `hypothesis_formation.py`
and `investigation_summary.py` parsers. `ConversationContext` will be
serialized to SQLite in Phase 2b (ADR-007); field renames require a migration.
Field renames or removals here break downstream consumers in ways tests may
not catch if mocks use the old schema.

---

### API endpoint paths

| Path | Method | Location |
|------|--------|----------|
| `/conversations` | POST | `api/routes.py` |
| `/conversations/{id}/messages` | POST | `api/routes.py` |
| `/conversations/{id}` | GET | `api/routes.py` |
| `/health` | GET | `api/routes.py` |

**Why protected**: external callers depend on these paths. A rename that
passes route tests still breaks any client (curl scripts, UI, integration
tests) that uses the old path.

---

### Environment variable names

Defined in `.env.example`. All names in that file are PROTECTED.

**Why protected**: operators set these in deployment. A rename in code that
is not reflected in operator documentation and existing `.env` files causes
a silent misconfiguration at deploy time.

---

### Knowledge base entry point

| Element | Location |
|---------|----------|
| `knowledge_loader.load()` as sole entry point | `war_room/knowledge_loader.py` |

**Why protected**: following release-agent ADR-019. If other modules bypass
`knowledge_loader` and read `knowledge/` files directly, changes to the
knowledge base structure (directory renames, file splits) can silently break
callers that tests don't cover.

---

### Existing ADRs

All files in `docs/03-decisions/` except this one. Per Atlas Principle 10:
decisions are immutable once accepted. Superseding an ADR requires a new ADR
that explicitly references the superseded one.

ADR-011 itself is the designated exception: it is updated by amendment (dated
entries in this document) rather than by supersession. No new ADR number is
created when registering an additional protected element.

---

## How to modify an existing protected element

1. Write a new ADR describing the change and why.
2. Identify all locations in the registry affected.
3. Update all affected locations atomically (single commit).
4. Amend this ADR with a dated entry noting the change and updated locations.
5. For MCP tool names: coordinate with upstream teams before the commit
   lands (bilateral contract per ADR-009).

## How to register a new protected element

If a new element meets the definition of PROTECTED (a silent-break risk not
caught by the test suite alone): add a row or entry to the relevant section
above, and append a dated amendment note at the end of this document.

---

## Related decisions

- Atlas Principle 9 — protected decisions
- Atlas Principle 10 — ADR immutability (ADR-011 is the designated exception)
- ADR-009 — MCP tool names as bilateral contract
- ADR-010 — skill prompt headers as parsing contract
- Release-agent ADR-014 — the pattern this follows
