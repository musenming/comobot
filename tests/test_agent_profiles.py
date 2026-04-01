"""Tests for agent profiles system."""

from __future__ import annotations

from comobot.agent.agents.profiles import AGENT_PROFILES, get_profile


class TestAgentProfile:
    def test_all_profiles_exist(self):
        assert "general" in AGENT_PROFILES
        assert "researcher" in AGENT_PROFILES
        assert "coder" in AGENT_PROFILES
        assert "analyst" in AGENT_PROFILES

    def test_general_has_all_tools(self):
        general = AGENT_PROFILES["general"]
        assert general.tools == ["*"]

    def test_researcher_limited_tools(self):
        researcher = AGENT_PROFILES["researcher"]
        assert "web_search" in researcher.tools
        assert "write_file" not in researcher.tools

    def test_coder_limited_tools(self):
        coder = AGENT_PROFILES["coder"]
        assert "write_file" in coder.tools
        assert "read_file" in coder.tools

    def test_get_profile_known(self):
        profile = get_profile("researcher")
        assert profile.name == "Researcher"

    def test_get_profile_unknown_falls_back(self):
        profile = get_profile("nonexistent")
        assert profile.name == "General"

    def test_filter_tools_wildcard(self):
        general = AGENT_PROFILES["general"]
        all_tools = ["read_file", "write_file", "exec", "web_search"]
        filtered = general.filter_tools(all_tools)
        assert filtered == all_tools

    def test_filter_tools_whitelist(self):
        researcher = AGENT_PROFILES["researcher"]
        all_tools = ["read_file", "write_file", "exec", "web_search", "memory_search"]
        filtered = researcher.filter_tools(all_tools)
        assert "web_search" in filtered
        assert "read_file" in filtered
        assert "write_file" not in filtered
        assert "exec" not in filtered

    def test_load_system_prompt(self):
        general = AGENT_PROFILES["general"]
        prompt = general.load_system_prompt()
        assert len(prompt) > 0  # Should load from prompts/general.md

    def test_profile_temperatures(self):
        assert AGENT_PROFILES["coder"].temperature == 0.0
        assert AGENT_PROFILES["researcher"].temperature == 0.2
        assert AGENT_PROFILES["general"].temperature == 0.1


class TestWorkspaceMigration:
    def test_migrate_creates_dirs(self, tmp_path):
        from comobot.agent.migration import migrate_workspace_v2

        migrate_workspace_v2(tmp_path)
        assert (tmp_path / "episodic").exists()
        assert (tmp_path / "feedback").exists()
        assert (tmp_path / "agents").exists()

    def test_migrate_idempotent(self, tmp_path):
        from comobot.agent.migration import migrate_workspace_v2

        migrate_workspace_v2(tmp_path)
        migrate_workspace_v2(tmp_path)  # Second call should not error
        assert (tmp_path / "episodic").exists()

    def test_migrate_preserves_existing(self, tmp_path):
        from comobot.agent.migration import migrate_workspace_v2

        (tmp_path / "episodic").mkdir()
        (tmp_path / "episodic" / "existing.md").write_text("keep me")
        migrate_workspace_v2(tmp_path)
        assert (tmp_path / "episodic" / "existing.md").read_text() == "keep me"
