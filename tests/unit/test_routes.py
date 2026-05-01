"""Tests for GET /sources/status (api/routes.py).

Mocks ping() at the routes module boundary so no MCP servers are needed.
TestClient is sync; asyncio_mode=auto applies only to async test functions.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DISABLE_OAUTH", "true")
    from api.main import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /sources/status
# ---------------------------------------------------------------------------

def test_sources_status_both_ok(client):
    with patch("api.routes.pulse_client.ping", new=AsyncMock(return_value=True)), \
         patch("api.routes.release_agent_client.ping", new=AsyncMock(return_value=True)):
        resp = client.get("/sources/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pulse"] == "ok"
    assert data["release_agent"] == "ok"


def test_sources_status_pulse_unreachable(client):
    with patch("api.routes.pulse_client.ping", new=AsyncMock(return_value=False)), \
         patch("api.routes.release_agent_client.ping", new=AsyncMock(return_value=True)):
        resp = client.get("/sources/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pulse"] == "unreachable"
    assert data["release_agent"] == "ok"


def test_sources_status_timeout_treated_as_unreachable(client):
    # Simulate a ping that exceeds the 3-second budget. _timed_ping catches
    # asyncio.TimeoutError (and all Exception) and returns False, so the
    # source is reported as unreachable. Using AsyncMock(side_effect=…) keeps
    # the coroutine properly awaited — no "coroutine never awaited" warning.
    with patch("api.routes.pulse_client.ping", new=AsyncMock(side_effect=asyncio.TimeoutError)), \
         patch("api.routes.release_agent_client.ping", new=AsyncMock(side_effect=asyncio.TimeoutError)):
        resp = client.get("/sources/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pulse"] == "unreachable"
    assert data["release_agent"] == "unreachable"
