from __future__ import annotations

import re
from pathlib import Path

_PROMPT_FILE = (
    Path(__file__).parent.parent.parent
    / "skills"
    / "release-metric-correlation"
    / "prompts"
    / "correlate.md"
)

# PROTECTED headers — must match exactly (ADR-011)
_CANDIDATES_RE = re.compile(r"^Candidate releases:", re.MULTILINE)


def build_message() -> dict:
    prompt = _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return {"role": "user", "content": prompt}


def has_finding(text: str) -> bool:
    """True if the response contains a release correlation finding."""
    return bool(_CANDIDATES_RE.search(text))
