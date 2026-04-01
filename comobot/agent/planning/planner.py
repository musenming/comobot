"""Task planner: decomposes complex tasks into executable steps using LLM."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from comobot.agent.planning.models import TaskPlan, TaskStep

if TYPE_CHECKING:
    from comobot.providers.base import LLMProvider

PLANNER_SYSTEM_PROMPT = """\
You are a task planner. Decompose complex requests into executable sub-steps.

Rules:
1. Each step must be atomic and independently executable
2. Clearly mark dependencies between steps
3. Assign the most appropriate agent type:
   - general: General conversation, simple queries
   - researcher: Information retrieval, web search, document reading
   - coder: Code writing, modification, debugging
   - analyst: Data analysis, comparison, summary reports
4. Keep steps between 2 and 6
5. Steps without dependencies will be executed in parallel

IMPORTANT: You MUST output ONLY a JSON object. No explanations, no markdown fences, no other text.

Example input: "Research competitors and write a summary report"
Example output:
{"goal":"Research competitors and write summary","steps":[{"id":"step_1","description":"Search for and collect competitor information","agent_type":"researcher","dependencies":[],"tools_hint":["web_search"]},{"id":"step_2","description":"Analyze collected data and write summary report","agent_type":"analyst","dependencies":["step_1"],"tools_hint":[]}]}

Now output your JSON plan:
"""


class TaskPlanner:
    """Uses LLM to decompose a task into an ordered plan."""

    def __init__(self, provider: LLMProvider, model: str | None = None, max_steps: int = 6):
        self._provider = provider
        self._model = model
        self._max_steps = max_steps

    async def plan(
        self,
        message: str,
        context: list[dict] | None = None,
        bootstrap: str | None = None,
    ) -> TaskPlan:
        """Generate a task plan from a user message.

        Args:
            message: The user's request.
            context: Optional prior conversation context.
            bootstrap: Optional pre-existing results from escalation (tool outputs already done).
        """
        user_content = message
        if bootstrap:
            user_content = (
                f"Context from prior work (already completed):\n{bootstrap}\n\n"
                f"Original request:\n{message}"
            )

        messages: list[dict] = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self._provider.chat(
                messages=messages,
                model=self._model,
                temperature=0,
                max_tokens=2048,
            )
        except Exception:
            logger.exception("Planner LLM call failed")
            return self._fallback_plan(message)

        return self._parse_plan(response.content, message)

    def _parse_plan(self, content: str | None, original_message: str) -> TaskPlan:
        """Parse the LLM planner response into a TaskPlan."""
        if not content:
            logger.warning("Planner returned empty content")
            return self._fallback_plan(original_message)

        data = self._extract_json(content)
        if not data or "steps" not in data:
            logger.warning(
                "Planner response not valid JSON plan: {}",
                content[:300] if content else "(empty)",
            )
            return self._fallback_plan(original_message)

        goal = data.get("goal", original_message)
        steps: list[TaskStep] = []
        for raw in data["steps"][: self._max_steps]:
            steps.append(
                TaskStep(
                    id=raw.get("id", f"step_{len(steps) + 1}"),
                    description=raw.get("description", ""),
                    agent_type=raw.get("agent_type", "general"),
                    dependencies=raw.get("dependencies", []),
                    tools_hint=raw.get("tools_hint", []),
                )
            )

        if not steps:
            logger.warning("Planner produced zero steps from: {}", content[:300])
            return self._fallback_plan(original_message)

        return TaskPlan(goal=goal, steps=steps, status="executing")

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract JSON from LLM response (handles markdown code blocks, mixed text)."""
        import re

        import json_repair

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Try finding a JSON object containing "steps" with balanced braces
        # Walk through text to find { ... } that contains "steps"
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                if depth == 0:
                    candidate = text[i : j + 1]
                    if '"steps"' in candidate:
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            pass
                    break
        # Last resort: use json_repair to fix common LLM JSON mistakes
        try:
            repaired = json_repair.loads(text)
            if isinstance(repaired, dict) and "steps" in repaired:
                return repaired
        except Exception:
            pass
        return None

    def _fallback_plan(self, message: str) -> TaskPlan:
        """Generate a single-step fallback plan when planning fails."""
        logger.warning("Planner failed, using single-step fallback")
        return TaskPlan(
            goal=message[:200],
            steps=[
                TaskStep(
                    id="step_1",
                    description=message,
                    agent_type="general",
                )
            ],
            status="executing",
        )
