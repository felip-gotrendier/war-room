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


# ---------------------------------------------------------------------------
# POST /conversations/{id}/messages/stream  (SSE smoke)
# ---------------------------------------------------------------------------


def test_stream_endpoint_unauthenticated_returns_401(client):
    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-s"})
    conv_id = create_resp.json()["id"]
    resp = client.post(f"/conversations/{conv_id}/messages/stream",
                       json={"message": "test"})
    assert resp.status_code == 401


def test_stream_endpoint_returns_event_stream(client):
    from unittest.mock import AsyncMock, patch
    from anthropic.types import Message
    from war_room import orchestrator as orch

    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-s"})
    conv_id = create_resp.json()["id"]

    fake_resp = Message(**{
        "id": "msg_t", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "Streamed reply"}],
        "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
        "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 5},
    })

    with patch.object(orch._client.messages, "create", new_callable=AsyncMock) as mock:
        mock.return_value = fake_resp
        with client.stream(
            "POST", f"/conversations/{conv_id}/messages/stream",
            headers={"X-User-Id": "sub-s"},
            json={"message": "test"},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            raw = b"".join(resp.iter_bytes()).decode()

    assert "event: text" in raw
    assert "event: done" in raw
    assert "Streamed reply" in raw


# ---------------------------------------------------------------------------
# _display_messages() unit tests
# ---------------------------------------------------------------------------


def test_conversation_view_has_header_title_data_role(client):
    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-hdr"})
    conv_id = create_resp.json()["id"]
    resp = client.get(f"/conversations/{conv_id}/view", headers={"X-User-Id": "sub-hdr"})
    assert resp.status_code == 200
    assert 'data-role="conv-header-title"' in resp.text


def test_display_messages_filters_skill_prompt():
    from api.ui_routes import _display_messages

    msgs = [{"role": "user", "content": "You are a funnel investigator.\n\nWhy did orders drop?"}]
    result = _display_messages(msgs)
    assert result == [{"role": "user", "content": "Why did orders drop?"}]


def test_display_messages_drops_tool_result():
    from api.ui_routes import _display_messages

    msgs = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "{}"}]}]
    result = _display_messages(msgs)
    assert result == []


def test_display_messages_keeps_assistant_message():
    from api.ui_routes import _display_messages

    msgs = [{"role": "assistant", "content": [{"type": "text", "text": "Here's the analysis."}]}]
    result = _display_messages(msgs)
    assert result == msgs


def test_display_messages_drops_skill_prompt_with_empty_question():
    from api.ui_routes import _display_messages

    # Skill prompt with no actual question (edge case)
    msgs = [{"role": "user", "content": "You are an investigator.\n\n"}]
    result = _display_messages(msgs)
    assert result == []


def test_display_messages_preserves_order():
    from api.ui_routes import _display_messages

    msgs = [
        {"role": "user", "content": "You are a router.\n\nFirst question"},
        {"role": "assistant", "content": [{"type": "text", "text": "Answer one"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]},
        {"role": "user", "content": "You are a router.\n\nSecond question"},
        {"role": "assistant", "content": [{"type": "text", "text": "Answer two"}]},
    ]
    result = _display_messages(msgs)
    assert len(result) == 4
    assert result[0] == {"role": "user", "content": "First question"}
    assert result[1]["role"] == "assistant"
    assert result[2] == {"role": "user", "content": "Second question"}
    assert result[3]["role"] == "assistant"


# ---------------------------------------------------------------------------
# conversation view — skill prompts must not appear in rendered HTML
# ---------------------------------------------------------------------------


def test_display_messages_hides_intermediate_assistant_between_skill_prompts():
    from api.ui_routes import _display_messages

    msgs = [
        {"role": "user", "content": "You are source-routing.\n\nWhy did orders drop?"},
        {"role": "assistant", "content": [{"type": "text", "text": "Sources to query in order: pulse, release_agent"}]},
        {"role": "user", "content": "You are funnel-investigator.\n\nWhy did orders drop?"},
        {"role": "assistant", "content": [{"type": "text", "text": "Final finding: orders dropped 12%."}]},
    ]
    result = _display_messages(msgs)
    assert len(result) == 2
    assert result[0] == {"role": "user", "content": "Why did orders drop?"}
    final_text = result[1]["content"][0]["text"]
    assert "Final finding" in final_text
    assert "Sources to query" not in final_text


def test_display_messages_multi_turn_shows_correct_final_replies():
    from api.ui_routes import _display_messages

    msgs = [
        {"role": "user", "content": "You are source-routing.\n\nQuestion A"},
        {"role": "assistant", "content": [{"type": "text", "text": "Plan A (intermediate)"}]},
        {"role": "user", "content": "You are funnel-investigator.\n\nQuestion A"},
        {"role": "assistant", "content": [{"type": "text", "text": "Reply A"}]},
        {"role": "user", "content": "You are source-routing.\n\nQuestion B"},
        {"role": "assistant", "content": [{"type": "text", "text": "Plan B (intermediate)"}]},
        {"role": "user", "content": "You are funnel-investigator.\n\nQuestion B"},
        {"role": "assistant", "content": [{"type": "text", "text": "Reply B"}]},
    ]
    result = _display_messages(msgs)
    assert len(result) == 4
    assert result[0] == {"role": "user", "content": "Question A"}
    assert result[1]["content"][0]["text"] == "Reply A"
    assert result[2] == {"role": "user", "content": "Question B"}
    assert result[3]["content"][0]["text"] == "Reply B"


def test_display_messages_includes_tool_cards():
    """Tool cards appear in display_messages between the PM question and final reply."""
    import json as _json
    from api.ui_routes import _display_messages

    result_payload = _json.dumps({
        "source": "pulse",
        "tool": "check_metric",
        "data": {"metric": "orders/count", "platforms": []},
        "coverage": {
            "requested": "x", "covered": "x",
            "is_complete": True, "gaps": [], "freshness_at": None,
        },
    })
    msgs = [
        {"role": "user", "content": "You are source-routing.\n\nWhy did orders drop?"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_1", "name": "check_metric",
             "input": {"metric_name": "orders/count", "days": 7}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_1", "content": result_payload},
        ]},
        {"role": "user", "content": "You are funnel-investigator.\n\nWhy did orders drop?"},
        {"role": "assistant", "content": [{"type": "text", "text": "Orders dropped 12%."}]},
    ]
    result = _display_messages(msgs)

    roles = [m["role"] for m in result]
    assert "tool_card" in roles

    cards = [m for m in result if m["role"] == "tool_card"]
    assert len(cards) == 1
    assert cards[0]["tool"] == "check_metric"
    assert cards[0]["source"] == "pulse"
    assert cards[0]["coverage"]["is_complete"] is True
    # tool_card must sit between PM question and final reply
    assert roles.index("tool_card") > roles.index("user")
    assert roles.index("tool_card") < roles.index("assistant")


def test_conversation_view_does_not_render_skill_prompts(client):
    from unittest.mock import AsyncMock, patch
    from anthropic.types import Message
    from war_room import orchestrator as orch

    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-sp"})
    conv_id = create_resp.json()["id"]

    fake_resp = Message(**{
        "id": "msg_sp", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "Here is my analysis."}],
        "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
        "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 5},
    })

    with patch.object(orch._client.messages, "create", new_callable=AsyncMock) as mock:
        mock.return_value = fake_resp
        client.post(
            f"/conversations/{conv_id}/messages/stream",
            headers={"X-User-Id": "sub-sp"},
            json={"message": "Why did orders drop?"},
        )

    resp = client.get(f"/conversations/{conv_id}/view", headers={"X-User-Id": "sub-sp"})
    assert resp.status_code == 200
    assert "You are " not in resp.text


def test_conversation_view_static_tool_card_rendered(client):
    """After a tool call, reloading the conversation renders a static tool card."""
    from unittest.mock import AsyncMock, patch
    from anthropic.types import Message
    from war_room import orchestrator as orch

    create_resp = client.post("/conversations", headers={"X-User-Id": "sub-tc"})
    conv_id = create_resp.json()["id"]

    tool_resp = Message(**{
        "id": "msg_tc1", "type": "message", "role": "assistant",
        "content": [{"type": "tool_use", "id": "tu_1", "name": "check_metric",
                     "input": {"metric_name": "orders/count", "days": 7}}],
        "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
        "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 5},
    })
    text_resp = Message(**{
        "id": "msg_tc2", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "Orders dropped."}],
        "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
        "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 5},
    })

    call_n = 0

    async def _side(*a, **kw):
        nonlocal call_n
        call_n += 1
        return tool_resp if call_n == 1 else text_resp

    dispatch_result = {
        "source": "pulse", "tool": "check_metric",
        "data": {"metric": "orders/count", "platforms": []},
        "coverage": {
            "requested": "x", "covered": "x",
            "is_complete": True, "gaps": [], "freshness_at": None,
        },
    }

    with patch.object(orch._client.messages, "create", side_effect=_side):
        with patch.object(orch, "_dispatch_tool", new=AsyncMock(return_value=dispatch_result)):
            client.post(
                f"/conversations/{conv_id}/messages/stream",
                headers={"X-User-Id": "sub-tc"},
                json={"message": "Why did orders drop?"},
            )

    resp = client.get(f"/conversations/{conv_id}/view", headers={"X-User-Id": "sub-tc"})
    assert resp.status_code == 200
    assert 'data-role="static-tool-card"' in resp.text
    assert 'data-tool="check_metric"' in resp.text
    assert 'data-source="pulse"' in resp.text

    # Verify data-ui-data is single-escaped (not double-escaped) and JS-parseable.
    # The browser decodes one level of HTML entities; JSON.parse must then succeed.
    import re, html as _html, json as _json

    m = re.search(r'data-ui-data="([^"]*)"', resp.text)
    assert m, "data-ui-data attribute not found"
    ui_data = _json.loads(_html.unescape(m.group(1)))
    assert ui_data.get("metric") == "orders/count"
    assert "platforms" in ui_data

    m2 = re.search(r'data-coverage="([^"]*)"', resp.text)
    assert m2, "data-coverage attribute not found"
    coverage = _json.loads(_html.unescape(m2.group(1)))
    assert "is_complete" in coverage
    assert "gaps" in coverage
