from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Coverage:
    requested: str
    covered: str
    is_complete: bool
    gaps: list[str]
    freshness_at: str | None


@dataclass
class WarRoomFinding:
    source: str          # "pulse" | "release_agent"
    tool: str            # MCP tool name that produced this finding
    data: dict[str, Any]
    coverage: Coverage


@dataclass
class ConversationContext:
    id: str
    user_id: str
    messages: list[dict[str, Any]]
    iteration_count: int = 0
    current_hypothesis: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IterationCapReached(Exception):
    pass
