from __future__ import annotations

import re
from pathlib import Path

_PROMPT_FILE = (
    Path(__file__).parent.parent.parent
    / "skills"
    / "investigation-summary"
    / "prompts"
    / "summarize.md"
)

# PROTECTED section headers — must match exactly (ADR-011)
_INVESTIGATION_RE = re.compile(r"^## Investigation", re.MULTILINE)
_FINDINGS_RE = re.compile(r"^## Findings", re.MULTILINE)
_HYPOTHESIS_RE = re.compile(r"^## Hypothesis", re.MULTILINE)
_OPEN_QUESTIONS_RE = re.compile(r"^## Open questions", re.MULTILINE)


def build_message() -> dict:
    prompt = _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return {"role": "user", "content": prompt}


def extract_document(text: str) -> str:
    """Return the markdown document from Claude's response.

    Strips any preamble before the first # heading. If no heading is found,
    returns the full text.
    """
    m = re.search(r"^# ", text, re.MULTILINE)
    return text[m.start():].strip() if m else text.strip()


def is_complete(text: str) -> bool:
    """True if the document contains all four required section headers."""
    return all(
        pat.search(text)
        for pat in (_INVESTIGATION_RE, _FINDINGS_RE, _HYPOTHESIS_RE, _OPEN_QUESTIONS_RE)
    )
