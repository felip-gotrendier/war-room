"""Smoke tests for UI routes.

These tests verify that the server starts, routes are registered correctly,
and basic HTML responses are returned.  They use FastAPI's TestClient so the
full ASGI app (including lifespan) runs, catching structural errors (missing
response_model=None, broken template loading, etc.) that unit tests miss.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))
    monkeypatch.setenv("DISABLE_OAUTH", "true")
    # Import after env vars are set so lifespan picks up DB_PATH.
    from api.main import app
    with TestClient(app, follow_redirects=False) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /  (landing)
# ---------------------------------------------------------------------------


def test_root_unauthenticated_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


def test_root_with_mock_auth_returns_html(client):
    resp = client.get("/", headers={"X-User-Id": "sub-smoke"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "war room" in resp.text


def test_root_html_contains_new_investigation_button(client):
    resp = client.get("/", headers={"X-User-Id": "sub-smoke"})
    assert "New investigation" in resp.text


# ---------------------------------------------------------------------------
# GET /conversations/{id}/view
# ---------------------------------------------------------------------------


def test_conversation_view_unknown_id_redirects_to_root(client):
    resp = client.get("/conversations/nonexistent/view", headers={"X-User-Id": "sub-smoke"})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_conversation_view_returns_html(client):
    # Create a conversation via the API first, then view it.
    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-smoke"})
    assert create_resp.status_code == 200
    conv_id = create_resp.json()["id"]

    resp = client.get(f"/conversations/{conv_id}/view", headers={"X-User-Id": "sub-smoke"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "war room" in resp.text


def test_conversation_view_wrong_user_redirects(client):
    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-owner"})
    conv_id = create_resp.json()["id"]

    resp = client.get(f"/conversations/{conv_id}/view", headers={"X-User-Id": "sub-other"})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_conversation_view_unauthenticated_redirects_to_login(client):
    resp = client.get("/conversations/any-id/view")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]
