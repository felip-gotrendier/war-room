from __future__ import annotations

import re
from pathlib import Path

_PROMPT_FILE = (
    Path(__file__).parent.parent.parent
    / "skills"
    / "hypothesis-formation"
    / "prompts"
    / "hypothesize.md"
)

# PROTECTED headers — must match exactly (ADR-011)
_HYPOTHESIS_RE = re.compile(r"^Hypothesis:\s*(.+)$", re.MULTILINE)
_CONFIDENCE_RE = re.compile(r"^Confidence:\s*(.+)$", re.MULTILINE)


def build_message() -> dict:
    prompt = _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return {"role": "user", "content": prompt}


def has_hypothesis(text: str) -> bool:
    return bool(_HYPOTHESIS_RE.search(text))


def extract_hypothesis_text(text: str) -> str:
    """Return the full hypothesis block (from 'Hypothesis:' to end of text)."""
    m = _HYPOTHESIS_RE.search(text)
    if not m:
        return ""
    return text[m.start():].strip()


def extract_confidence(text: str) -> str | None:
    m = _CONFIDENCE_RE.search(text)
    return m.group(1).strip() if m else None
