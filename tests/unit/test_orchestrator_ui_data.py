"""Unit tests for orchestrator._compact_ui_data.

Verifies that the helper extracts the minimal display payload for each tool
type without touching external services.
"""
from __future__ import annotations

from war_room.orchestrator import _compact_ui_data


def _result(tool: str, data: dict, *, is_complete: bool = True) -> dict:
    return {
        "source": "pulse",
        "tool": tool,
        "data": data,
        "coverage": {"is_complete": is_complete, "gaps": [], "freshness_at": None},
    }


def test_check_metric_extracts_sparkline():
    result = _result("check_metric", {
        "metric": "orders/count",
        "platforms": [
            {"platform": "mx_android", "series": [
                {"date": "2026-04-01", "value": 0.92},
                {"date": "2026-04-02", "value": 0.88},
                {"date": "2026-04-03", "value": 0.85},
            ]},
        ],
    })
    ui = _compact_ui_data("check_metric", result)
    assert ui["metric"] == "orders/count"
    assert ui["sparkline"] == [0.92, 0.88, 0.85]


def test_check_metric_uses_first_platform():
    result = _result("check_metric", {
        "metric": "cvr",
        "platforms": [
            {"platform": "mx_android", "series": [{"date": "2026-04-01", "value": 0.5}]},
            {"platform": "mx_ios",     "series": [{"date": "2026-04-01", "value": 0.9}]},
        ],
    })
    ui = _compact_ui_data("check_metric", result)
    assert ui["sparkline"] == [0.5]


def test_check_metric_empty_platforms_returns_empty_sparkline():
    result = _result("check_metric", {"metric": "x", "platforms": []})
    ui = _compact_ui_data("check_metric", result)
    assert ui == {"metric": "x", "sparkline": []}


def test_check_metric_missing_data_field():
    result = _result("check_metric", {})
    ui = _compact_ui_data("check_metric", result)
    assert ui == {"metric": "", "sparkline": []}


def test_get_recent_anomalies_extracts_count():
    result = _result("get_recent_anomalies", {
        "anomalies": [{"metric": "a"}, {"metric": "b"}, {"metric": "c"}],
    })
    ui = _compact_ui_data("get_recent_anomalies", result)
    assert ui == {"anomaly_count": 3}


def test_get_recent_anomalies_empty():
    result = _result("get_recent_anomalies", {"anomalies": []})
    ui = _compact_ui_data("get_recent_anomalies", result)
    assert ui == {"anomaly_count": 0}


def test_get_releases_extracts_count():
    result = _result("get_releases", {
        "releases": [{"id": "v1"}, {"id": "v2"}],
    })
    result["source"] = "release_agent"
    ui = _compact_ui_data("get_releases", result)
    assert ui == {"release_count": 2}


def test_unknown_tool_returns_empty_dict():
    result = _result("trigger_scan", {"scan_accepted": True})
    ui = _compact_ui_data("trigger_scan", result)
    assert ui == {}


def test_get_release_returns_empty_dict():
    result = _result("get_release", {"release": {"id": "v1.2.3"}})
    result["source"] = "release_agent"
    ui = _compact_ui_data("get_release", result)
    assert ui == {}
