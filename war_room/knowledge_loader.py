from __future__ import annotations

from pathlib import Path

_KNOWLEDGE_ROOT = Path(__file__).parent.parent / "knowledge"


def load() -> str:
    """Return the full system prompt string assembled from all knowledge files.

    This is the sole entry point to the knowledge/ directory (ADR-011).
    No other module reads from knowledge/ directly.
    """
    sections: list[str] = []

    sections.append(_load_sources_section())
    sections.append(_read(_KNOWLEDGE_ROOT / "metrics" / "funnel-metrics.md"))
    sections.append(_read(_KNOWLEDGE_ROOT / "repo-platform-mapping.md"))
    sections.append(_load_playbooks_section())

    return "\n\n---\n\n".join(s for s in sections if s)


def _load_sources_section() -> str:
    sources_dir = _KNOWLEDGE_ROOT / "sources"
    files = sorted(sources_dir.glob("*.md"))
    # Exclude the README from the system prompt — it is editorial guidance only
    source_files = [f for f in files if f.name != "README.md"]
    if not source_files:
        return ""
    parts = ["# Connected sources\n"]
    for path in source_files:
        parts.append(_read(path))
    return "\n\n".join(parts)


def _load_playbooks_section() -> str:
    playbooks_dir = _KNOWLEDGE_ROOT / "investigation-playbooks"
    files = sorted(playbooks_dir.glob("*.md"))
    playbook_files = [f for f in files if f.name != "README.md"]
    if not playbook_files:
        return ""
    parts = ["# Investigation playbooks\n"]
    for path in playbook_files:
        parts.append(_read(path))
    return "\n\n".join(parts)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()
