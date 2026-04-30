from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from api.auth_utils import COOKIE_NAME, AuthUser, get_session_user
from api.models import (
    ConversationStateResponse,
    MessageRequest,
    MessageResponse,
    NewConversationResponse,
    SummarizeResponse,
)
from war_room import orchestrator
from war_room.conversation_repository import (
    ConversationAccessDenied,
    ConversationNotFound,
    ConversationRepository,
)
from war_room.db import get_db_path
from war_room.models import ConversationContext, IterationCapReached

router = APIRouter()


# ---------------------------------------------------------------------------
# Repository dependency (app.state.repo set by lifespan in main.py)
# ---------------------------------------------------------------------------

def _get_repo(request: Request) -> ConversationRepository:
    return request.app.state.repo


# ---------------------------------------------------------------------------
# Auth dependency
#
# Priority order:
#   1. war_room_session cookie (OAuth) — used when GOOGLE_CLIENT_ID is set
#   2. X-User-Id header (mock auth) — fallback when OAuth is not configured
#      or DISABLE_OAUTH=true.  Supports CI and dev without a Google Cloud Project.
#
# If a session cookie is present but expired/invalid, we return 401 immediately
# and do NOT fall back to the mock header — the user must log in again.
# ---------------------------------------------------------------------------

def _oauth_enabled() -> bool:
    return (
        bool(os.environ.get("GOOGLE_CLIENT_ID"))
        and os.environ.get("DISABLE_OAUTH", "false").lower() != "true"
    )


def _require_user(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> AuthUser:
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        user = get_session_user(get_db_path(), session_id)
        if user is not None:
            return user
        # Cookie present but session invalid or expired — do not fall back.
        raise HTTPException(
            status_code=401,
            detail="Session expired — please log in again at /auth/login",
        )

    if not _oauth_enabled() and x_user_id:
        return AuthUser(user_id=x_user_id, user_email=x_user_id)

    raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Routes (paths are PROTECTED — ADR-011)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/conversations", response_model=NewConversationResponse)
async def create_conversation(
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> NewConversationResponse:
    ctx = repo.create(user_id=user.user_id, user_email=user.user_email)
    return NewConversationResponse(
        id=ctx.id,
        user_id=ctx.user_id,
        iteration_count=ctx.iteration_count,
        created_at=ctx.created_at,
    )


@router.post("/conversations/{id}/messages", response_model=MessageResponse)
async def send_message(
    id: str,
    body: MessageRequest,
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> MessageResponse:
    ctx = _load_or_raise(id, user.user_id, repo)

    if ctx.iteration_count >= 15:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "iteration_cap_reached",
                "message": (
                    "This investigation has reached its 15-iteration limit. "
                    "You can view the current findings, publish the investigation, "
                    "or open a new conversation to continue."
                ),
                "iteration_count": ctx.iteration_count,
            },
        )

    try:
        reply, ctx = await orchestrator.turn(ctx, body.message)
    except IterationCapReached:
        repo.save(ctx, user_email=user.user_email)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "iteration_cap_reached",
                "message": (
                    "Investigation reached the 15-iteration limit during this turn. "
                    "Findings so far are preserved."
                ),
                "iteration_count": ctx.iteration_count,
            },
        )

    repo.save(ctx, user_email=user.user_email)
    return MessageResponse(
        reply=reply,
        iteration_count=ctx.iteration_count,
        hypothesis=ctx.current_hypothesis,
    )


@router.get("/conversations/{id}", response_model=ConversationStateResponse)
async def get_conversation(
    id: str,
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> ConversationStateResponse:
    ctx = _load_or_raise(id, user.user_id, repo)
    return ConversationStateResponse(
        id=ctx.id,
        user_id=ctx.user_id,
        iteration_count=ctx.iteration_count,
        cap_reached=ctx.iteration_count >= 15,
        current_hypothesis=ctx.current_hypothesis,
        created_at=ctx.created_at,
        last_active_at=ctx.last_active_at,
    )


@router.post("/conversations/{id}/summarize", response_model=SummarizeResponse)
async def summarize_conversation(
    id: str,
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> SummarizeResponse:
    ctx = _load_or_raise(id, user.user_id, repo)
    if not ctx.current_hypothesis:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_hypothesis",
                "message": (
                    "No hypothesis has been formed in this investigation. "
                    "Continue the investigation before generating a document."
                ),
            },
        )
    document = await orchestrator.summarize(ctx)
    repo.save(ctx, user_email=user.user_email)
    return SummarizeResponse(document=document)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_or_raise(id: str, user_id: str, repo: ConversationRepository) -> ConversationContext:
    try:
        return repo.load(id, user_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except ConversationAccessDenied:
        raise HTTPException(status_code=403, detail="Conversation belongs to another user")
