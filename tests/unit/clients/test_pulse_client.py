from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from war_room.clients import pulse_client
from war_room.models import Coverage, WarRoomFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mcp_result(payload: dict):
    block = MagicMock()
    block.text = json.dumps(payload)
    result = MagicMock()
    result.content = [block]
    return result


def _mock_call(payload: dict):
    return patch.object(pulse_client, "_call", new=AsyncMock(return_value=payload))


# ---------------------------------------------------------------------------
# check_metric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_metric_success():
    payload = {
        "data": {
            "metric": "users_product_list/active",
            "platforms": [
                {
                    "platform": "mx_android",
                    "series": [{"date": "2026-04-20", "value": 0.87}],
                }
            ],
        },
        "coverage": {
            "requested": {"metric_name": "users_product_list/active", "days": 14},
            "covered": {"metric_name": "users_product_list/active", "days": 14},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T08:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await pulse_client.check_metric("users_product_list/active", days=14)

    assert isinstance(finding, WarRoomFinding)
    assert finding.source == "pulse"
    assert finding.tool == "check_metric"
    assert "platforms" in finding.data
    assert finding.coverage.is_complete is True
    assert finding.coverage.gaps == []


@pytest.mark.asyncio
async def test_check_metric_error_synthesises_coverage():
    payload = {
        "error": {
            "code": "DATA_NOT_FOUND",
            "retryable": False,
            "message": "Metric not found",
        }
    }
    with _mock_call(payload):
        finding = await pulse_client.check_metric("unknown/metric", days=7)

    assert "error" in finding.data
    assert finding.coverage.is_complete is False
    assert "DATA_NOT_FOUND" in finding.coverage.gaps[0]


@pytest.mark.asyncio
async def test_check_metric_partial_coverage():
    payload = {
        "data": {
            "metric": "users_checkout/active",
            "platforms": [{"platform": "mx_android", "series": []}],
        },
        "coverage": {
            "requested": {"metric_name": "users_checkout/active", "days": 14},
            "covered": {"metric_name": "users_checkout/active", "days": 10},
            "is_complete": False,
            "gaps": ["co_android data unavailable"],
            "freshness_at": "2026-04-27T08:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await pulse_client.check_metric("users_checkout/active")

    assert finding.coverage.is_complete is False
    assert finding.coverage.gaps == ["co_android data unavailable"]


# ---------------------------------------------------------------------------
# get_recent_anomalies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_recent_anomalies_empty():
    payload = {
        "data": {"anomalies": []},
        "coverage": {
            "requested": {"days": 7},
            "covered": {"days": 7},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T08:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await pulse_client.get_recent_anomalies(days=7)

    assert finding.data["anomalies"] == []
    assert finding.coverage.is_complete is True


@pytest.mark.asyncio
async def test_get_recent_anomalies_with_anomaly():
    payload = {
        "data": {
            "anomalies": [
                {
                    "metric": "users_checkout/active",
                    "platform": "mx_android",
                    "onset_date": "2026-04-22",
                    "severity": "high",
                    "description": "30% drop",
                }
            ]
        },
        "coverage": {
            "requested": {"days": 14},
            "covered": {"days": 14},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T08:00:00Z",
        },
    }
    with _mock_call(payload):
        finding = await pulse_client.get_recent_anomalies(days=14)

    assert len(finding.data["anomalies"]) == 1
    assert finding.data["anomalies"][0]["severity"] == "high"


# ---------------------------------------------------------------------------
# trigger_scan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_scan_records_timestamp():
    payload = {"data": {"scan_accepted": True, "message": "Scan triggered."}}
    with _mock_call(payload):
        finding = await pulse_client.trigger_scan()

    assert finding.data["scan_accepted"] is True
    assert "triggered_at" in finding.data
    assert "get_recent_anomalies" in finding.data["note"]
    assert finding.coverage.is_complete is False


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retryable_error_retries_once():
    retryable_payload = {
        "error": {"code": "SOURCE_UNAVAILABLE", "retryable": True, "message": "down"}
    }
    success_payload = {
        "data": {"anomalies": []},
        "coverage": {
            "requested": {"days": 7},
            "covered": {"days": 7},
            "is_complete": True,
            "gaps": [],
            "freshness_at": "2026-04-27T08:00:00Z",
        },
    }
    call_mock = AsyncMock(side_effect=[Exception("timeout"), success_payload])
    with patch.object(pulse_client, "_call", call_mock):
        finding = await pulse_client.get_recent_anomalies(days=7)

    assert call_mock.call_count == 2
    assert finding.coverage.is_complete is True


@pytest.mark.asyncio
async def test_non_retryable_error_does_not_retry():
    call_mock = AsyncMock(
        return_value={
            "error": {"code": "AUTH_FAILURE", "retryable": False, "message": "auth failed"}
        }
    )
    with patch.object(pulse_client, "_call", call_mock):
        finding = await pulse_client.check_metric("some/metric")

    assert call_mock.call_count == 1
    assert "error" in finding.data
