from __future__ import annotations

from pydantic import BaseModel


class NewConversationResponse(BaseModel):
    id: str
    user_id: str
    iteration_count: int
    created_at: str


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    reply: str
    iteration_count: int
    hypothesis: str | None = None


class ConversationStateResponse(BaseModel):
    id: str
    user_id: str
    iteration_count: int
    cap_reached: bool
    current_hypothesis: str | None
    created_at: str
    last_active_at: str


class SummarizeResponse(BaseModel):
    document: str
