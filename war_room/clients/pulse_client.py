from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from war_room.models import Coverage, WarRoomFinding

_RETRYABLE_CODES = {"SOURCE_UNAVAILABLE", "PARTIAL_FAILURE", "RATE_LIMITED"}
_NON_RETRYABLE_CODES = {"AUTH_FAILURE", "INVALID_PARAMS", "DATA_NOT_FOUND"}


def _url() -> str:
    return os.environ["PULSE_MCP_URL"]


async def check_metric(
    metric_name: str,
    days: int = 14,
    platform: str | None = None,
) -> WarRoomFinding:
    args: dict = {"metric_name": metric_name, "days": days}
    if platform:
        args["platform"] = platform
    raw = await _call_with_retry("check_metric", args)
    return _parse_check_metric(raw, args)


async def get_recent_anomalies(
    days: int = 7,
    severity: str | None = None,
) -> WarRoomFinding:
    args: dict = {"days": days}
    if severity:
        args["severity"] = severity
    raw = await _call_with_retry("get_recent_anomalies", args)
    return _parse_anomalies(raw, args)


async def trigger_scan() -> WarRoomFinding:
    triggered_at = datetime.now(timezone.utc).isoformat()
    raw = await _call_with_retry("trigger_scan", {})
    return _parse_trigger_scan(raw, triggered_at)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_check_metric(raw: dict, requested_args: dict) -> WarRoomFinding:
    coverage = _extract_coverage(raw, requested_args)
    if "error" in raw:
        return WarRoomFinding(
            source="pulse",
            tool="check_metric",
            data={"error": raw["error"]},
            coverage=coverage,
        )
    return WarRoomFinding(
        source="pulse",
        tool="check_metric",
        data=raw.get("data", {}),
        coverage=coverage,
    )


def _parse_anomalies(raw: dict, requested_args: dict) -> WarRoomFinding:
    coverage = _extract_coverage(raw, requested_args)
    if "error" in raw:
        return WarRoomFinding(
            source="pulse",
            tool="get_recent_anomalies",
            data={"error": raw["error"]},
            coverage=coverage,
        )
    return WarRoomFinding(
        source="pulse",
        tool="get_recent_anomalies",
        data=raw.get("data", {}),
        coverage=coverage,
    )


def _parse_trigger_scan(raw: dict, triggered_at: str) -> WarRoomFinding:
    data = raw.get("data", {})
    return WarRoomFinding(
        source="pulse",
        tool="trigger_scan",
        data={
            "scan_accepted": data.get("scan_accepted", False),
            "triggered_at": triggered_at,
            "note": "Fresh data available in ~60 seconds via get_recent_anomalies.",
        },
        coverage=Coverage(
            requested="trigger_scan",
            covered="",
            is_complete=False,
            gaps=["scan in progress — data not yet available"],
            freshness_at=None,
        ),
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
    # MCP SDK returns result.content as a list of content blocks
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
    # Synthesize when absent (e.g. error path without coverage)
    err = raw.get("error", {})
    code = err.get("code", "UNKNOWN") if isinstance(err, dict) else "UNKNOWN"
    return Coverage(
        requested=json.dumps(requested_args),
        covered="",
        is_complete=False,
        gaps=[f"pulse error: {code}"],
        freshness_at=None,
    )
