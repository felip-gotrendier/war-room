from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

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
from war_room.models import ConversationContext, IterationCapReached

router = APIRouter()


# ---------------------------------------------------------------------------
# Repository dependency (app.state.repo set by lifespan in main.py)
# ---------------------------------------------------------------------------

def _get_repo(request: Request) -> ConversationRepository:
    return request.app.state.repo


# ---------------------------------------------------------------------------
# Auth (Phase 2a mock — replaced by OAuth session check in Phase 2b.1 Commit 4)
# ---------------------------------------------------------------------------

def _require_user(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    return x_user_id


# ---------------------------------------------------------------------------
# Routes (paths are PROTECTED — ADR-011)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/conversations", response_model=NewConversationResponse)
async def create_conversation(
    user_id: str = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> NewConversationResponse:
    # Phase 2a: X-User-Id value used as email placeholder.
    # Commit 4 replaces this with real user_email from the OAuth session.
    ctx = repo.create(user_id=user_id, user_email=user_id)
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
    user_id: str = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> MessageResponse:
    ctx = _load_or_raise(id, user_id, repo)

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
        repo.save(ctx, user_email=user_id)  # Phase 2a: user_id as email placeholder
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

    repo.save(ctx, user_email=user_id)  # Phase 2a: user_id as email placeholder
    return MessageResponse(
        reply=reply,
        iteration_count=ctx.iteration_count,
        hypothesis=ctx.current_hypothesis,
    )


@router.get("/conversations/{id}", response_model=ConversationStateResponse)
async def get_conversation(
    id: str,
    user_id: str = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> ConversationStateResponse:
    ctx = _load_or_raise(id, user_id, repo)
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
    user_id: str = Depends(_require_user),
    repo: ConversationRepository = Depends(_get_repo),
) -> SummarizeResponse:
    ctx = _load_or_raise(id, user_id, repo)
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
    repo.save(ctx, user_email=user_id)  # Phase 2a: user_id as email placeholder
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
