"""Data models for the planning engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TaskStep:
    """A single step in a task plan."""

    id: str  # "step_1", "step_2", ...
    description: str
    agent_type: str = "general"  # "general" | "researcher" | "coder" | "analyst"
    dependencies: list[str] = field(default_factory=list)  # IDs of prerequisite steps
    tools_hint: list[str] = field(default_factory=list)
    status: str = "pending"  # "pending" | "running" | "done" | "failed"
    result: str | None = None
    error: str | None = None
    structured_result: dict | None = None  # Parsed structured output (summary, findings, etc.)


@dataclass
class TaskPlan:
    """A plan for executing a complex task."""

    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "planning"  # "planning" | "executing" | "reflecting" | "done" | "failed"
    reflection: str | None = None
    revision_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def current_step_index(self) -> int:
        """Return the index of the first non-done step, or len(steps) if all done."""
        for i, step in enumerate(self.steps):
            if step.status not in ("done",):
                return i
        return len(self.steps)

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed") for s in self.steps)

    def summary(self) -> str:
        """Return a human-readable summary of the plan."""
        lines = [f"Goal: {self.goal}", f"Status: {self.status}", "Steps:"]
        for s in self.steps:
            deps = f" (depends: {', '.join(s.dependencies)})" if s.dependencies else ""
            lines.append(f"  [{s.status}] {s.id}: {s.description}{deps}")
        if self.reflection:
            lines.append(f"Reflection: {self.reflection}")
        return "\n".join(lines)
