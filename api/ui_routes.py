from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.auth_utils import COOKIE_NAME, AuthUser, get_session_user
from war_room.conversation_repository import ConversationAccessDenied, ConversationNotFound
from war_room.db import get_db_path

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


templates.env.filters["message_text"] = _message_text


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


@router.get("/", response_class=HTMLResponse)
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


@router.get("/conversations/{id}/view", response_class=HTMLResponse)
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
        },
    )
