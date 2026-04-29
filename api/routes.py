from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.models import (
    ConversationStateResponse,
    MessageRequest,
    MessageResponse,
    NewConversationResponse,
    SummarizeResponse,
)
from war_room import orchestrator
from war_room.models import ConversationContext, IterationCapReached

router = APIRouter()

# Phase 2a in-memory store — replaced by SQLite in Phase 2b (ADR-007)
_conversations: dict[str, ConversationContext] = {}


# ---------------------------------------------------------------------------
# Auth (Phase 2a mock — ADR-010)
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
async def create_conversation(user_id: str = Depends(_require_user)) -> NewConversationResponse:
    ctx = orchestrator.create_conversation(user_id)
    _conversations[ctx.id] = ctx
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
) -> MessageResponse:
    ctx = _get_conversation(id, user_id)

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
        _conversations[id] = ctx
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

    _conversations[id] = ctx
    return MessageResponse(
        reply=reply,
        iteration_count=ctx.iteration_count,
        hypothesis=ctx.current_hypothesis,
    )


@router.get("/conversations/{id}", response_model=ConversationStateResponse)
async def get_conversation(
    id: str,
    user_id: str = Depends(_require_user),
) -> ConversationStateResponse:
    ctx = _get_conversation(id, user_id)
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
) -> SummarizeResponse:
    ctx = _get_conversation(id, user_id)
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
    _conversations[id] = ctx
    return SummarizeResponse(document=document)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conversation(id: str, user_id: str) -> ConversationContext:
    ctx = _conversations.get(id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if ctx.user_id != user_id:
        raise HTTPException(status_code=403, detail="Conversation belongs to another user")
    return ctx
