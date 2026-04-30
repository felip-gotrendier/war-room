from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic

from war_room import knowledge_loader
from war_room.models import ConversationContext, IterationCapReached
from war_room.skills import (
    funnel_investigation,
    hypothesis_formation,
    investigation_summary,
    release_metric_correlation,
    source_routing,
)

_MODEL = "claude-sonnet-4-6"

# Tool schemas exposed to Claude (names are PROTECTED — ADR-011)
_TOOLS: list[dict] = [
    {
        "name": "check_metric",
        "description": "Retrieve a funnel metric time series from pulse for the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name": {"type": "string", "description": "Full metric identifier, e.g. users_product_list/active"},
                "days": {"type": "integer", "description": "Number of days to look back", "default": 14},
                "platform": {"type": "string", "description": "Optional platform filter, e.g. mx_android"},
            },
            "required": ["metric_name"],
        },
    },
    {
        "name": "get_recent_anomalies",
        "description": "Return metrics that pulse has flagged as anomalous in the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look back", "default": 7},
                "severity": {"type": "string", "description": "Optional filter: high, medium, or low"},
            },
        },
    },
    {
        "name": "trigger_scan",
        "description": "Request a fresh pulse computation (fire-and-forget). Use when get_recent_anomalies data is stale.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_releases",
        "description": "Return releases from release-agent for a repository in a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository name, e.g. android, backend"},
                "date_range": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "ISO8601 start date"},
                        "end": {"type": "string", "description": "ISO8601 end date"},
                    },
                    "required": ["start", "end"],
                },
            },
            "required": ["repo", "date_range"],
        },
    },
    {
        "name": "get_release",
        "description": "Return metadata for a specific release by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "id": {"type": "string", "description": "Release identifier as returned by get_releases"},
            },
            "required": ["repo", "id"],
        },
    },
    {
        "name": "explain_release",
        "description": "Return a narrative summary of what a specific release changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "id": {"type": "string"},
            },
            "required": ["repo", "id"],
        },
    },
]

_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def create_conversation(user_id: str) -> ConversationContext:
    return ConversationContext(
        id=str(uuid.uuid4()),
        user_id=user_id,
        messages=[],
    )


async def turn(
    context: ConversationContext,
    pm_message: str,
    event_queue: asyncio.Queue | None = None,
) -> tuple[str, ConversationContext]:
    """Process one PM turn and return (assistant_text, updated_context).

    Raises IterationCapReached if the cap has been hit.
    If event_queue is provided, emits tool_start/tool_complete dicts per tool call.
    """
    if context.iteration_count >= 15:
        raise IterationCapReached

    # First turn: inject source-routing
    if not context.messages:
        context.messages.append(source_routing.build_message(pm_message))
    else:
        context.messages.append({"role": "user", "content": pm_message})

    final_text = await _run_loop(context, event_queue=event_queue)

    context.last_active_at = datetime.now(timezone.utc).isoformat()
    return final_text, context


async def summarize(context: ConversationContext) -> str:
    """Produce the investigation document (ADR-006). Does not count as a turn."""
    context.messages.append(investigation_summary.build_message())
    response = await _claude_call(context)
    text = _extract_text(response)
    context.messages.append({"role": "assistant", "content": _serialize_content(response.content)})
    return investigation_summary.extract_document(text)


# ---------------------------------------------------------------------------
# Internal loop
# ---------------------------------------------------------------------------

async def _run_loop(
    context: ConversationContext,
    event_queue: asyncio.Queue | None = None,
) -> str:
    """Run the Claude ↔ tool loop until Claude produces a text-only response."""
    while True:
        if context.iteration_count >= 15:
            raise IterationCapReached

        response = await _claude_call(context)
        context.iteration_count += 1
        context.last_active_at = datetime.now(timezone.utc).isoformat()

        text = _extract_text(response)
        context.messages.append({"role": "assistant", "content": _serialize_content(response.content)})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            # No tool calls — inject skill prompts if needed
            await _maybe_inject_hypothesis(context, text)
            return text

        # Execute all tool calls and collect results
        tool_results_content: list[dict] = []
        for block in tool_uses:
            if event_queue is not None:
                await event_queue.put({"type": "tool_start", "tool": block.name, "input": block.input})
            result = await _dispatch_tool(block.name, block.input)
            if event_queue is not None:
                await event_queue.put({
                    "type": "tool_complete",
                    "tool": block.name,
                    "source": result.get("source", "unknown"),
                    "coverage": {
                        "is_complete": result["coverage"]["is_complete"],
                        "gaps": result["coverage"]["gaps"],
                    },
                    "ui_data": _compact_ui_data(block.name, result),
                })
            tool_results_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        # Inject skill prompts as text blocks in the same user message.
        # trigger_scan is excluded from pulse_ran: it is fire-and-forget with
        # no analyzable data — injecting funnel-investigation would be premature.
        pulse_ran = any(b.name in {"check_metric", "get_recent_anomalies"} for b in tool_uses)
        release_ran = any(b.name in {"get_releases", "get_release", "explain_release"} for b in tool_uses)

        if pulse_ran:
            tool_results_content.append({
                "type": "text",
                "text": funnel_investigation.build_message()["content"],
            })
        if release_ran:
            tool_results_content.append({
                "type": "text",
                "text": release_metric_correlation.build_message()["content"],
            })

        context.messages.append({"role": "user", "content": tool_results_content})


async def _maybe_inject_hypothesis(context: ConversationContext, last_text: str) -> None:
    """Inject hypothesis-formation prompt when findings are present."""
    if hypothesis_formation.has_hypothesis(last_text):
        # Already produced a hypothesis in this response
        context.current_hypothesis = hypothesis_formation.extract_hypothesis_text(last_text)
        return

    has_metric = funnel_investigation.has_finding(last_text)
    has_release = release_metric_correlation.has_finding(last_text)

    # Trigger hypothesis when we have at least a metric finding plus either a
    # release finding or a release gap (the gap itself is informative evidence)
    if has_metric and (has_release or _has_repo_gap(context)):
        if context.iteration_count < 15:
            context.messages.append(hypothesis_formation.build_message())
            response = await _claude_call(context)
            context.iteration_count += 1
            hyp_text = _extract_text(response)
            context.messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            if hypothesis_formation.has_hypothesis(hyp_text):
                context.current_hypothesis = hypothesis_formation.extract_hypothesis_text(hyp_text)


def _has_repo_gap(context: ConversationContext) -> bool:
    """True if any prior tool result contained a REPO_NOT_FOUND gap."""
    for msg in context.messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    c = item.get("content", "")
                    if "REPO_NOT_FOUND" in c or "not confirmed" in c.lower():
                        return True
    return False


def _compact_ui_data(tool_name: str, result: dict) -> dict:
    """Extract minimal display data from a tool result for the SSE tool_complete event."""
    data = result.get("data", {})
    if tool_name == "check_metric":
        platforms = data.get("platforms", [])
        if platforms:
            # Use the first platform as a representative sparkline.
            # Multi-platform display would clutter the card (β tradeoff).
            # If a platform-specific anomaly matters, the assistant text will call it out.
            series = platforms[0].get("series", [])
            return {
                "metric": data.get("metric", ""),
                "sparkline": [p["value"] for p in series],
            }
        return {"metric": data.get("metric", ""), "sparkline": []}
    if tool_name == "get_recent_anomalies":
        return {"anomaly_count": len(data.get("anomalies", []))}
    if tool_name == "get_releases":
        return {"release_count": len(data.get("releases", []))}
    return {}


def _serialize_content(content: list) -> list[dict]:
    """Convert SDK content blocks (TextBlock, ToolUseBlock, …) to plain dicts.

    ctx.messages contract is list[dict] throughout the codebase. The Anthropic
    SDK returns Pydantic model instances; calling .model_dump() normalises them
    before they enter ctx.messages, so json.dumps() in repo.save() never sees
    a non-serializable type.
    """
    return [b if isinstance(b, dict) else b.model_dump() for b in content]


async def _dispatch_tool(name: str, input_args: dict) -> dict:
    from war_room.clients import pulse_client, release_agent_client

    if name == "check_metric":
        finding = await pulse_client.check_metric(**input_args)
    elif name == "get_recent_anomalies":
        finding = await pulse_client.get_recent_anomalies(**input_args)
    elif name == "trigger_scan":
        finding = await pulse_client.trigger_scan()
    elif name == "get_releases":
        finding = await release_agent_client.get_releases(**input_args)
    elif name == "get_release":
        finding = await release_agent_client.get_release(**input_args)
    elif name == "explain_release":
        finding = await release_agent_client.explain_release(**input_args)
    else:
        return {"error": f"Unknown tool: {name}"}

    return {
        "source": finding.source,
        "tool": finding.tool,
        "data": finding.data,
        "coverage": {
            "requested": finding.coverage.requested,
            "covered": finding.coverage.covered,
            "is_complete": finding.coverage.is_complete,
            "gaps": finding.coverage.gaps,
            "freshness_at": finding.coverage.freshness_at,
        },
    }


async def _claude_call(context: ConversationContext) -> Any:
    system = knowledge_loader.load()
    return await _client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=system,
        tools=_TOOLS,
        messages=context.messages,
    )


def _extract_text(response: Any) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""
