# Sources

Each file in this directory describes one connected MCP source. The orchestrator
reads all files here at session start and injects them into the system prompt
as the "Connected sources" section (ADR-004).

## File format

```markdown
# <source name>

**What it knows**: <2-3 sentences on scope and data coverage>

**What it does NOT know**: <1-2 sentences of explicit anti-patterns>

**Available tools**:
- `<tool_name>`: <one line — when to call this tool, not what it does mechanically>
```

The "What it does NOT know" field is mandatory. Without it, the LLM routes
questions that look thematically relevant but are out of scope.

Tool descriptions answer "when to call" not "what the parameters are".
Parameter schemas live in the MCP tool definition (ADR-003).

## Adding a source

1. Create `knowledge/sources/<name>.md` using the format above.
2. Ensure the MCP server is registered in war-room's tool set.
3. Both steps are required — see `knowledge/README.md`.

## Currently connected sources

- `pulse.md` — funnel metric data
- `release-agent.md` — release history and release narratives
