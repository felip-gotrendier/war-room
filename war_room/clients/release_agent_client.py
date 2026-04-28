from __future__ import annotations

import json
import os

from mcp import ClientSession
from mcp.client.streamablehttp import streamablehttp_client

from war_room.models import Coverage, WarRoomFinding

_RETRYABLE_CODES = {"SOURCE_UNAVAILABLE", "PARTIAL_FAILURE", "RATE_LIMITED"}
# REPO_NOT_FOUND is treated as a coverage gap, not retried
_NON_RETRYABLE_CODES = {"AUTH_FAILURE", "INVALID_PARAMS", "REPO_NOT_FOUND", "RELEASE_NOT_FOUND", "INVALID_DATE_RANGE"}

_REPO_NOT_CONFIRMED_GAP = (
    "No confirmed repositories available — release-agent risk maps pending "
    "tech lead validation"
)


def _url() -> str:
    return os.environ["RELEASE_AGENT_MCP_URL"]


async def get_releases(repo: str, date_range: dict) -> WarRoomFinding:
    args = {"repo": repo, "date_range": date_range}
    raw = await _call_with_retry("get_releases", args)
    return _parse_get_releases(raw, args)


async def get_release(repo: str, id: str) -> WarRoomFinding:
    args = {"repo": repo, "id": id}
    raw = await _call_with_retry("get_release", args)
    return _parse_single_release(raw, args, "get_release")


async def explain_release(repo: str, id: str) -> WarRoomFinding:
    args = {"repo": repo, "id": id}
    raw = await _call_with_retry("explain_release", args)
    return _parse_explain_release(raw, args)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_get_releases(raw: dict, requested_args: dict) -> WarRoomFinding:
    code = _error_code(raw)

    if code == "REPO_NOT_FOUND":
        # Graceful degradation — treated as coverage gap, not a system error
        return WarRoomFinding(
            source="release_agent",
            tool="get_releases",
            data={"releases": []},
            coverage=Coverage(
                requested=json.dumps(requested_args),
                covered="",
                is_complete=False,
                gaps=[_REPO_NOT_CONFIRMED_GAP],
                freshness_at=None,
            ),
        )

    coverage = _extract_coverage(raw, requested_args)
    if code:
        return WarRoomFinding(
            source="release_agent",
            tool="get_releases",
            data={"error": raw.get("error")},
            coverage=coverage,
        )

    releases = raw.get("releases", raw.get("data", {}).get("releases", []))
    return WarRoomFinding(
        source="release_agent",
        tool="get_releases",
        data={"releases": releases},
        coverage=coverage,
    )


def _parse_single_release(raw: dict, requested_args: dict, tool: str) -> WarRoomFinding:
    coverage = _extract_coverage(raw, requested_args)
    if _error_code(raw):
        return WarRoomFinding(
            source="release_agent",
            tool=tool,
            data={"error": raw.get("error")},
            coverage=coverage,
        )
    # release-agent returns {"release": {...}} or {"data": {"id": ...}}
    release = raw.get("release") or raw.get("data", {})
    return WarRoomFinding(
        source="release_agent",
        tool=tool,
        data={"release": release},
        coverage=coverage,
    )


def _parse_explain_release(raw: dict, requested_args: dict) -> WarRoomFinding:
    coverage = _extract_coverage(raw, requested_args)
    if _error_code(raw):
        return WarRoomFinding(
            source="release_agent",
            tool="explain_release",
            data={"error": raw.get("error")},
            coverage=coverage,
        )
    # release-agent returns {"explanation": {...}} or {"data": {...}}
    explanation = raw.get("explanation") or raw.get("data", {})
    return WarRoomFinding(
        source="release_agent",
        tool="explain_release",
        data={"explanation": explanation},
        coverage=coverage,
    )


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

async def _call_with_retry(tool_name: str, arguments: dict) -> dict:
    try:
        return await _call(tool_name, arguments)
    except Exception as exc:
        raw = _exc_to_raw(exc)
        code = _error_code(raw)
        if code in _RETRYABLE_CODES:
            try:
                return await _call(tool_name, arguments)
            except Exception as retry_exc:
                return _exc_to_raw(retry_exc)
        return raw


async def _call(tool_name: str, arguments: dict) -> dict:
    url = _url()
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    text = _extract_text(result)
    return json.loads(text)


def _extract_text(result) -> str:  # type: ignore[no-untyped-def]
    for block in result.content:
        if hasattr(block, "text"):
            return block.text
    raise ValueError(f"No text block in MCP result: {result}")


def _exc_to_raw(exc: Exception) -> dict:
    return {
        "error": {
            "code": "SOURCE_UNAVAILABLE",
            "retryable": True,
            "message": str(exc),
        }
    }


def _error_code(raw: dict) -> str | None:
    err = raw.get("error")
    if isinstance(err, dict):
        return err.get("code")
    return None


def _extract_coverage(raw: dict, requested_args: dict) -> Coverage:
    cov = raw.get("coverage")
    if cov:
        return Coverage(
            requested=json.dumps(cov.get("requested", requested_args)),
            covered=json.dumps(cov.get("covered", {})),
            is_complete=cov.get("is_complete", False),
            gaps=cov.get("gaps", []),
            freshness_at=cov.get("freshness_at"),
        )
    # release-agent omits coverage on errors — synthesise it
    err = raw.get("error", {})
    code = err.get("code", "UNKNOWN") if isinstance(err, dict) else "UNKNOWN"
    return Coverage(
        requested=json.dumps(requested_args),
        covered="",
        is_complete=False,
        gaps=[f"release-agent error: {code}"],
        freshness_at=None,
    )
