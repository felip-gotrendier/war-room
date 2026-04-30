from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.auth_utils import COOKIE_NAME, AuthUser, get_session_user
from api.models import (
    ConversationListItem,
    ConversationStateResponse,
    InvestigationListItem,
    MessageRequest,
    MessageResponse,
    NewConversationResponse,
    PublishRequest,
    PublishResponse,
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
from war_room.saved_investigation_repository import (
    SavedInvestigationNotFound,
    SavedInvestigationRepository,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Repository dependency (app.state.repo set by lifespan in main.py)
# ---------------------------------------------------------------------------

def _get_repo(request: Request) -> ConversationRepository:
    return request.app.state.repo


def _get_saved_inv_repo(request: Request) -> SavedInvestigationRepository:
    return request.app.state.saved_inv_repo


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

    was_first_turn = ctx.iteration_count == 0

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

    if was_first_turn:
        raw = body.message
        title = raw[:60].rstrip() + ("…" if len(raw) > 60 else "")
        repo.update_on_first_turn(ctx.id, title=title, original_question=raw)

    repo.save(ctx, user_email=user.user_email)
    return MessageResponse(
        reply=reply,
        iteration_count=ctx.iteration_count,
        hypothesis=ctx.current_hypothesis,
    )


@router.post("/conversations/{id}/messages/stream", response_model=None)
async def stream_message(
    id: str,
    body: MessageRequest,
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> EventSourceResponse:
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

    was_first_turn = ctx.iteration_count == 0
    queue: asyncio.Queue = asyncio.Queue()

    async def _run() -> None:
        try:
            reply, updated = await orchestrator.turn(ctx, body.message, event_queue=queue)
            if was_first_turn:
                raw = body.message
                title = raw[:60].rstrip() + ("…" if len(raw) > 60 else "")
                repo.update_on_first_turn(updated.id, title=title, original_question=raw)
            repo.save(updated, user_email=user.user_email)
            await queue.put({"type": "text", "text": reply})
            await queue.put({"type": "done", "iteration_count": updated.iteration_count})
        except IterationCapReached:
            repo.save(ctx, user_email=user.user_email)
            await queue.put({
                "type": "error",
                "code": "iteration_cap_reached",
                "iteration_count": ctx.iteration_count,
            })
        except Exception as exc:
            await queue.put({"type": "error", "detail": str(exc)})
        finally:
            await queue.put(None)  # sentinel — signals end of stream

    async def _generate():
        task = asyncio.create_task(_run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield {"event": event["type"], "data": json.dumps(event)}
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(_generate())


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


@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> list[ConversationListItem]:
    rows = repo.list_by_user(user.user_id)
    return [ConversationListItem(**row) for row in rows]


@router.post("/conversations/{id}/publish", response_model=PublishResponse)
async def publish_conversation(
    id: str,
    body: PublishRequest,
    user: AuthUser = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
    inv_repo: SavedInvestigationRepository = Depends(_get_saved_inv_repo),
) -> PublishResponse:
    ctx = _load_or_raise(id, user.user_id, repo)
    if not ctx.current_hypothesis:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_hypothesis",
                "message": (
                    "No hypothesis has been formed in this investigation. "
                    "Continue the investigation before publishing."
                ),
            },
        )
    metadata = repo.get_metadata(id, user.user_id)
    document = await orchestrator.summarize(ctx)
    title = body.title or metadata["title"]
    result = inv_repo.publish(
        conversation_id=id,
        published_by=user.user_id,
        published_by_email=user.user_email,
        title=title,
        document=document,
        original_question=metadata["original_question"] or "",
        final_confidence=ctx.current_hypothesis,
    )
    repo.save(ctx, user_email=user.user_email)
    return PublishResponse(
        id=result["id"],
        document=result["document"],
        title=result["title"],
        published_at=result["published_at"],
        is_republish=result["is_republish"],
    )


@router.get("/investigations", response_model=list[InvestigationListItem])
async def list_investigations(
    user: AuthUser = Depends(_require_user),
    inv_repo: SavedInvestigationRepository = Depends(_get_saved_inv_repo),
) -> list[InvestigationListItem]:
    rows = inv_repo.list_all()
    return [
        InvestigationListItem(
            id=r["id"],
            conversation_id=r["conversation_id"],
            title=r["title"],
            published_by_email=r["published_by_email"],
            published_at=r["published_at"],
            original_question=r["original_question"],
            metrics_mentioned=json.loads(r["metrics_mentioned"]),
            final_confidence=r["final_confidence"],
        )
        for r in rows
    ]


@router.delete("/investigations/{id}", status_code=204)
async def delete_investigation(
    id: str,
    user: AuthUser = Depends(_require_user),
    inv_repo: SavedInvestigationRepository = Depends(_get_saved_inv_repo),
) -> None:
    # ADR-005: any authenticated war-room user can delete any investigation.
    # Team-trust model — this is an explicit policy, not missing access control.
    try:
        inv_repo.delete(id)
    except SavedInvestigationNotFound:
        raise HTTPException(status_code=404, detail="Investigation not found")


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
