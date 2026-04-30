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


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: str
    last_active_at: str
    iteration_count: int


class PublishRequest(BaseModel):
    title: str | None = None


class PublishResponse(BaseModel):
    id: str
    document: str
    title: str
    published_at: str
    is_republish: bool


class InvestigationListItem(BaseModel):
    id: str
    conversation_id: str
    title: str
    published_by_email: str
    published_at: str
    original_question: str
    metrics_mentioned: list[str]
    final_confidence: str
