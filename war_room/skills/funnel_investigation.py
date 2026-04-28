from __future__ import annotations

import re
from pathlib import Path

_PROMPT_FILE = Path(__file__).parent.parent.parent / "skills" / "funnel-investigation" / "prompts" / "investigate.md"

# PROTECTED headers — must match exactly (ADR-011)
_METRIC_RE = re.compile(r"^Metric:\s*(.+)$", re.MULTILINE)
_SUMMARY_RE = re.compile(r"^Summary:\s*(.+)$", re.MULTILINE)


def build_message() -> dict:
    prompt = _PROMPT_FILE.read_text(encoding="utf-8").strip()
    return {"role": "user", "content": prompt}


def has_finding(text: str) -> bool:
    """True if the response contains at least one funnel-investigation finding."""
    return bool(_METRIC_RE.search(text))


def extract_metric_names(text: str) -> list[str]:
    return [m.group(1).strip() for m in _METRIC_RE.finditer(text)]
