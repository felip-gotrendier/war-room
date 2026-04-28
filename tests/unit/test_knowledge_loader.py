from __future__ import annotations

from war_room import knowledge_loader


def test_load_returns_string():
    result = knowledge_loader.load()
    assert isinstance(result, str)
    assert len(result) > 0


def test_load_includes_pulse_source():
    result = knowledge_loader.load()
    assert "check_metric" in result
    assert "pulse" in result.lower()


def test_load_includes_release_agent_source():
    result = knowledge_loader.load()
    assert "get_releases" in result
    assert "release-agent" in result.lower()


def test_load_includes_funnel_metrics():
    result = knowledge_loader.load()
    assert "users_product_list" in result or "product_list" in result


def test_load_includes_repo_mapping():
    result = knowledge_loader.load()
    assert "android" in result


def test_load_includes_playbooks():
    result = knowledge_loader.load()
    assert "investigation" in result.lower()


def test_load_excludes_readme_content():
    result = knowledge_loader.load()
    # The sources README contains editorial guidance not intended for Claude
    assert "how to update this file" not in result.lower()


def test_load_includes_bi_tool():
    result = knowledge_loader.load()
    assert "bi-tool" in result.lower()
