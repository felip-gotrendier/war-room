"""Integration test: orchestrator.turn() → ConversationRepository.save().

Verifies that SDK content blocks (TextBlock, ToolUseBlock) returned by the
Anthropic API are normalised to plain dicts before repo.save() serialises
ctx.messages via json.dumps().

Mocks only the Anthropic API call — no MCP servers required; the test
always runs without a skip guard.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from anthropic.types import Message

from war_room import orchestrator
from war_room.conversation_repository import ConversationRepository
from war_room.db import init_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_message(content: list[dict]) -> Message:
    """Build a real anthropic.types.Message from plain content dicts.

    The Message constructor converts the dicts to SDK objects (TextBlock,
    ToolUseBlock, …), replicating what the live Anthropic API returns.
    """
    return Message(**{
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


@pytest.fixture
def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_schema(db_path)
    return ConversationRepository(db_path)


# ---------------------------------------------------------------------------
# Primary bug regression: TextBlock is not JSON-serialisable
# ---------------------------------------------------------------------------


async def test_turn_then_save_does_not_raise(repo):
    """repo.save() must not raise TypeError after a real orchestrator turn."""
    ctx = orchestrator.create_conversation(user_id="sub-test")
    fake_resp = _fake_message([{"type": "text", "text": "Entenc la pregunta."}])

    with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock:
        mock.return_value = fake_resp
        reply, ctx = await orchestrator.turn(ctx, "hola")

    # This was the failing call — must not raise
    repo.save(ctx, user_email="user@example.com")


async def test_saved_messages_are_loadable(repo):
    """Messages saved after a turn must survive a full load round-trip."""
    ctx = repo.create(user_id="sub-rt", user_email="user@example.com")
    fake_resp = _fake_message([{"type": "text", "text": "Primera resposta."}])

    with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock:
        mock.return_value = fake_resp
        _, ctx = await orchestrator.turn(ctx, "hola")

    repo.save(ctx, user_email="user@example.com")
    loaded = repo.load(ctx.id, "sub-rt")

    assert loaded.iteration_count == 1
    assistant_msgs = [m for m in loaded.messages if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1


# ---------------------------------------------------------------------------
# Contract: ctx.messages contains only plain dicts after a turn
# ---------------------------------------------------------------------------


async def test_all_content_blocks_are_dicts_after_turn():
    """ctx.messages contract: every content block must be a plain dict."""
    ctx = orchestrator.create_conversation(user_id="sub-contract")
    fake_resp = _fake_message([{"type": "text", "text": "Resposta."}])

    with patch.object(orchestrator._client.messages, "create", new_callable=AsyncMock) as mock:
        mock.return_value = fake_resp
        _, ctx = await orchestrator.turn(ctx, "hola")

    for msg in ctx.messages:
        assert isinstance(msg, dict), f"message is not a dict: {type(msg)}"
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                assert isinstance(block, dict), (
                    f"content block is not a dict: {type(block)}"
                )


# ---------------------------------------------------------------------------
# Tool-use blocks: ToolUseBlock must also be serialisable
# ---------------------------------------------------------------------------


async def test_tool_use_blocks_are_serialisable(repo):
    """ToolUseBlock content from a tool-call response must survive json.dumps."""
    ctx = repo.create(user_id="sub-tool", user_email="user@example.com")

    # First response: assistant requests a tool call
    tool_resp = _fake_message([
        {"type": "tool_use", "id": "tu_abc", "name": "check_metric",
         "input": {"metric_name": "orders/count", "days": 7}},
    ])
    # Second response (after tool results are fed back): text-only reply
    text_resp = _fake_message([{"type": "text", "text": "Mètrica revisada."}])

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return tool_resp if call_count == 1 else text_resp

    with patch.object(orchestrator._client.messages, "create", side_effect=_side_effect):
        # Also mock _dispatch_tool to avoid hitting real MCP servers
        with patch.object(
            orchestrator, "_dispatch_tool",
            new=AsyncMock(return_value={
                "source": "pulse", "tool": "check_metric",
                "data": {"values": []},
                "coverage": {
                    "requested": "orders/count", "covered": "orders/count",
                    "is_complete": True, "gaps": [], "freshness_at": None,
                },
            }),
        ):
            _, ctx = await orchestrator.turn(ctx, "Com va orders/count?")

    # Must not raise
    repo.save(ctx, user_email="user@example.com")

    loaded = repo.load(ctx.id, "sub-tool")
    assert loaded.iteration_count >= 1
