from __future__ import annotations

import html
import json
import os
from markupsafe import Markup
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.auth_utils import COOKIE_NAME, AuthUser, get_session_user
from war_room.conversation_repository import ConversationAccessDenied, ConversationNotFound
from war_room.db import get_db_path
from war_room.orchestrator import compact_ui_data

router = APIRouter()

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _message_text(content: Any) -> str:
    """Extract display text from a message content field (str or content-block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _tool_input_summary(input_dict: dict, tool: str) -> str:
    """Mirror of stream.js toolInputSummary — pre-compute meta text for static cards."""
    if not input_dict:
        return ""
    if tool == "check_metric":
        return input_dict.get("metric_name", "")
    if tool == "get_recent_anomalies":
        return f"last {input_dict.get('days', 7)}d"
    if tool == "get_releases":
        return input_dict.get("repo", "")
    if tool in ("get_release", "explain_release"):
        repo = input_dict.get("repo", "")
        rid = input_dict.get("id", "")
        return f"{repo}/{rid}" if repo else ""
    return ""


def _extract_tool_cards(messages: list[dict]) -> list[dict]:
    """Scan a PM turn slice for tool_use/tool_result pairs and return tool_card dicts.

    Edge cases:
    - tool_use with no matching tool_result (tool never returned): silently skipped.
    - Multiple tool_use blocks in the same assistant message: all are iterated.
    - Malformed tool_result JSON: silently skipped.
    """
    cards = []
    for k, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            continue
        # Find the next user message in this slice that contains tool_result blocks.
        next_user_content: list[dict] = []
        for m in messages[k + 1:]:
            if m.get("role") == "user" and isinstance(m.get("content"), list):
                next_user_content = m["content"]
                break
        for tool_use in tool_uses:
            tool_name = tool_use.get("name", "")
            tool_id = tool_use.get("id", "")
            tool_input = tool_use.get("input", {})
            result_json = None
            for item in next_user_content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "tool_result"
                    and item.get("tool_use_id") == tool_id
                ):
                    result_json = item.get("content", "")
                    break
            if not result_json:
                continue
            try:
                result_data = json.loads(result_json)
                cov = result_data.get("coverage", {})
                cards.append({
                    "role": "tool_card",
                    "tool": tool_name,
                    "input": tool_input,
                    "summary": _tool_input_summary(tool_input, tool_name),
                    "source": result_data.get("source", "unknown"),
                    "coverage": {
                        "is_complete": cov.get("is_complete", True),
                        "gaps": cov.get("gaps", []),
                    },
                    "ui_data": compact_ui_data(tool_name, result_data),
                })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return cards


def _display_messages(messages: list[dict]) -> list[dict]:
    # Heuristic assumptions — any of these breaking silently corrupts the view:
    #   1. Skill prompts start with "You are ".
    #   2. The PM question is the last \n\n-delimited section of each skill prompt.
    #   3. All skill prompts within a single PM turn embed the same PM question
    #      (used to detect turn boundaries between consecutive skill calls).
    #   4. The last assistant text message in a PM turn block is the final reply.
    # Phase 2c: replace with explicit message tagging in the orchestrator
    # (e.g. a "_skill_prompt": True field) instead of text-matching.
    #
    # Algorithm: group consecutive skill prompts that share the same extracted PM
    # question into a single "PM turn block". Within each block, show:
    #   (1) the PM question once, (2) the last assistant message with text content.
    # All intermediate assistant messages (e.g. source-routing planning text) and
    # all tool_result user messages are hidden.
    result: list[dict] = []
    n = len(messages)
    i = 0

    while i < n:
        msg = messages[i]
        role = msg.get("role")
        content = msg.get("content")

        if role == "user" and isinstance(content, list):
            # tool_result — never displayed
            i += 1
            continue

        if role == "user" and isinstance(content, str) and content.startswith("You are "):
            pm_question = content.split("\n\n")[-1].strip()

            # Scan forward to find the end of this PM turn block.
            # A new PM turn starts when a skill prompt with a DIFFERENT PM question appears.
            j = i + 1
            while j < n:
                m = messages[j]
                mc = m.get("content")
                if (
                    m.get("role") == "user"
                    and isinstance(mc, str)
                    and mc.startswith("You are ")
                    and mc.split("\n\n")[-1].strip() != pm_question
                ):
                    break
                j += 1

            # Within [i, j), keep only the last assistant message that has text.
            last_asst: dict | None = None
            for k in range(i, j):
                if messages[k].get("role") == "assistant":
                    if _message_text(messages[k].get("content", "")):
                        last_asst = messages[k]

            if pm_question:
                result.append({"role": "user", "content": pm_question})
            result.extend(_extract_tool_cards(messages[i:j]))
            if last_asst is not None:
                result.append(last_asst)

            i = j
            continue

        # Non-skill-prompt, non-tool-result message — pass through as-is.
        result.append(msg)
        i += 1

    return result


templates.env.filters["message_text"] = _message_text
templates.env.filters["attr_json"] = lambda obj: Markup(html.escape(json.dumps(obj)))


def _oauth_enabled() -> bool:
    return (
        bool(os.environ.get("GOOGLE_CLIENT_ID"))
        and os.environ.get("DISABLE_OAUTH", "false").lower() != "true"
    )


def _get_user(request: Request) -> AuthUser | None:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        return get_session_user(get_db_path(), session_id)
    if not _oauth_enabled() and (x_uid := request.headers.get("x-user-id")):
        return AuthUser(user_id=x_uid, user_email=x_uid)
    return None


@router.get("/", response_class=HTMLResponse, response_model=None)
async def landing(request: Request) -> HTMLResponse | RedirectResponse:
    user = _get_user(request)
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)

    repo = request.app.state.repo
    conversations = repo.list_by_user(user.user_id)
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"user": user, "conversations": conversations},
    )


@router.get("/conversations/{id}/view", response_class=HTMLResponse, response_model=None)
async def conversation_view(
    id: str, request: Request
) -> HTMLResponse | RedirectResponse:
    user = _get_user(request)
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)

    repo = request.app.state.repo
    inv_repo = request.app.state.saved_inv_repo

    try:
        ctx = repo.load(id, user.user_id)
        metadata = repo.get_metadata(id, user.user_id)
    except (ConversationNotFound, ConversationAccessDenied):
        return RedirectResponse("/", status_code=302)

    conversations = repo.list_by_user(user.user_id)
    published = inv_repo.get_by_conversation(id)

    return templates.TemplateResponse(
        request,
        "conversation.html",
        {
            "user": user,
            "ctx": ctx,
            "metadata": metadata,
            "conversations": conversations,
            "published": published,
            "cap_reached": ctx.iteration_count >= 15,
            "display_messages": _display_messages(ctx.messages),
        },
    )
