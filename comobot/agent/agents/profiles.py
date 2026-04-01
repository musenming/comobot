"""Agent profile definitions for multi-agent dispatch.

Each profile configures a virtual agent with its own system prompt,
allowed tool subset, model override, and iteration limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class AgentProfile:
    """Configuration for a specialized agent type."""

    name: str
    system_prompt_file: str  # Filename under prompts/
    tools: list[str] = field(default_factory=lambda: ["*"])  # ["*"] = all tools
    model_override: str | None = None
    max_iterations: int = 40
    temperature: float = 0.1

    def load_system_prompt(self) -> str:
        """Load the system prompt from the prompts directory."""
        path = _PROMPTS_DIR / self.system_prompt_file
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"You are a {self.name} agent."

    def filter_tools(self, all_tool_names: list[str]) -> list[str]:
        """Return the subset of tool names this profile is allowed to use."""
        if "*" in self.tools:
            return all_tool_names
        return [t for t in all_tool_names if t in self.tools]


AGENT_PROFILES: dict[str, AgentProfile] = {
    "general": AgentProfile(
        name="General",
        system_prompt_file="general.md",
        tools=["*"],
        max_iterations=40,
        temperature=0.1,
    ),
    "researcher": AgentProfile(
        name="Researcher",
        system_prompt_file="researcher.md",
        tools=[
            "web_search",
            "web_fetch",
            "read_file",
            "list_dir",
            "memory_search",
            "memory_get",
            "knowhow_search",
        ],
        max_iterations=15,
        temperature=0.2,
    ),
    "coder": AgentProfile(
        name="Coder",
        system_prompt_file="coder.md",
        tools=[
            "read_file",
            "write_file",
            "edit_file",
            "list_dir",
            "exec",
            "web_search",
        ],
        max_iterations=30,
        temperature=0.0,
    ),
    "analyst": AgentProfile(
        name="Analyst",
        system_prompt_file="analyst.md",
        tools=[
            "read_file",
            "web_search",
            "web_fetch",
            "exec",
            "memory_search",
            "memory_get",
        ],
        max_iterations=20,
        temperature=0.1,
    ),
}


def get_profile(name: str) -> AgentProfile:
    """Look up an agent profile by name, falling back to 'general'."""
    return AGENT_PROFILES.get(name, AGENT_PROFILES["general"])
