"""Variable substitution for workflow orchestrator."""

from __future__ import annotations

import re
from typing import Any


class VariableContext:
    """Manages variables during workflow execution."""

    def __init__(self):
        self._vars: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._vars[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._vars.get(key, default)

    def resolve(self, template: str) -> str:
        """Replace {{var.name}} patterns in template string."""

        def replacer(match):
            key = match.group(1).strip()
            val = self._vars.get(key, match.group(0))
            return _escape_prompt_injection(str(val))

        return re.sub(r"\{\{(.+?)\}\}", replacer, template)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._vars)


def _escape_prompt_injection(text: str) -> str:
    """Escape known prompt injection markers in variable values."""
    markers = ["<system>", "</system>", "<|system|>", "<|endoftext|>"]
    for marker in markers:
        text = text.replace(marker, f"[{marker}]")
    return text
