from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from war_room.clients import release_agent_client
from war_room.models import WarRoomFinding


def _mock_call(payload: dict):
    return patch.object(release_agent_client, "_call", new=AsyncMock(return_value=payload))


# ---------------------------------------------------------------------------
# get_releases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_releases_success():
    payload = {
        "releases": [
            {"id": "android-v4.12.1", "deployed_at": "2026-04-21T14:30:00Z"}
        ],
        "coverage": {
            "requested": {"repo": "android", "date_range": {"start": "2026-04-14", "end": "2026-04-28"}},
            "covered": {"repo": "android", "date_range": {"start": "2026-04-14", "end": "2026-04-28"}},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T12:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await release_agent_client.get_releases(
            "android", {"start": "2026-04-14", "end": "2026-04-28"}
        )

    assert finding.source == "release_agent"
    assert finding.tool == "get_releases"
    assert len(finding.data["releases"]) == 1
    assert finding.coverage.is_complete is True


@pytest.mark.asyncio
async def test_get_releases_empty():
    payload = {
        "releases": [],
        "coverage": {
            "requested": {"repo": "android", "date_range": {"start": "2026-04-01", "end": "2026-04-10"}},
            "covered": {"repo": "android", "date_range": {"start": "2026-04-01", "end": "2026-04-10"}},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T12:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await release_agent_client.get_releases(
            "android", {"start": "2026-04-01", "end": "2026-04-10"}
        )

    assert finding.data["releases"] == []
    assert finding.coverage.is_complete is True


@pytest.mark.asyncio
async def test_get_releases_repo_not_found_is_coverage_gap():
    payload = {
        "error": {
            "code": "REPO_NOT_FOUND",
            "retryable": False,
            "message": "Repository android not found",
        }
    }
    with _mock_call(payload):
        finding = await release_agent_client.get_releases(
            "android", {"start": "2026-04-14", "end": "2026-04-28"}
        )

    # REPO_NOT_FOUND must be a coverage gap, not an error in finding.data
    assert finding.data == {"releases": []}
    assert finding.coverage.is_complete is False
    assert "pending" in finding.coverage.gaps[0].lower() or "not confirmed" in finding.coverage.gaps[0].lower()


@pytest.mark.asyncio
async def test_get_releases_source_unavailable_synthesises_coverage():
    payload = {
        "error": {
            "code": "SOURCE_UNAVAILABLE",
            "retryable": True,
            "message": "DB down",
        }
    }
    with _mock_call(payload):
        finding = await release_agent_client.get_releases(
            "android", {"start": "2026-04-14", "end": "2026-04-28"}
        )

    assert finding.coverage.is_complete is False
    assert "SOURCE_UNAVAILABLE" in finding.coverage.gaps[0]


# ---------------------------------------------------------------------------
# explain_release
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explain_release_success():
    payload = {
        "explanation": {
            "id": "android-v4.12.1",
            "repo": "android",
            "summary": "Cambios en layout de tarjetas de producto.",
            "areas_affected": ["product_list"],
            "pr_count": 3,
        },
        "coverage": {
            "requested": {"repo": "android", "id": "android-v4.12.1"},
            "covered": {"repo": "android", "id": "android-v4.12.1"},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T12:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await release_agent_client.explain_release("android", "android-v4.12.1")

    assert finding.tool == "explain_release"
    assert "summary" in finding.data["explanation"]
    assert finding.coverage.is_complete is True


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_source_unavailable_retries_once():
    success = {
        "releases": [],
        "coverage": {
            "requested": {},
            "covered": {},
            "is_complete": True,
            "gaps": [],
            "freshness_at": None,
        },
    }
    call_mock = AsyncMock(side_effect=[Exception("timeout"), success])
    with patch.object(release_agent_client, "_call", call_mock):
        finding = await release_agent_client.get_releases(
            "backend", {"start": "2026-04-01", "end": "2026-04-10"}
        )

    assert call_mock.call_count == 2
