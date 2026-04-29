from __future__ import annotations

from pathlib import Path

_PROMPT_FILE = Path(__file__).parent.parent.parent / "skills" / "source-routing" / "prompts" / "routing.md"


def build_message(pm_question: str) -> dict:
    """Return the user message that triggers source-routing output."""
    prompt = _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return {
        "role": "user",
        "content": f"{prompt}\n\n{pm_question}",
    }


def is_gap_declaration(text: str) -> bool:
    """True if Claude declared no connected source can answer the question."""
    return "The question requires" in text


def is_query_plan(text: str) -> bool:
    return "Sources to query" in text
