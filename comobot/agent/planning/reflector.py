"""Reflector: checks execution results against the original goal."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from comobot.agent.planning.models import TaskPlan

if TYPE_CHECKING:
    from comobot.providers.base import LLMProvider

REFLECTOR_PROMPT = """\
You are a task reviewer. The user's original goal was:
{goal}

The execution results for each step are:
{step_results}

Please evaluate:
1. Do the results completely answer the user's question?
2. Are there any omissions or errors?
3. If revisions are needed, specify which step IDs need re-execution

Output format (JSON only, no other text):
{{
  "satisfied": true/false,
  "summary": "Final response content for the user",
  "revisions": []
}}
"""

SYNTHESIS_PROMPT = """\
You are a result synthesizer. The user's original goal was:
{goal}

Below are the results from multiple execution steps. Synthesize them into a single, \
coherent response that directly addresses the user's goal.

Rules:
1. PRESERVE DETAIL — this is a comprehensive report, not a summary. Keep all important \
information including file paths, code snippets, data points, and analysis
2. Remove redundancy — do not repeat information that appears in multiple steps
3. Maintain logical flow — organize by topic, not by step order
4. Write as if you are directly answering the user — no "Step 1 found..." framing
5. If steps produced conflicting information, note the discrepancy
6. Use the same language as the user's goal
7. The output should be AT LEAST as detailed as the combined step results — do NOT shorten

Step results:
{step_results}

Output your synthesized response directly (no JSON, no meta-commentary):
"""

PLAN_SUMMARY_PROMPT = """\
You are a task plan reviewer. The user's original goal was:
{goal}

The plan was divided into the following steps, each executed by an agent. \
Summarize the EXECUTION PROCESS — what each step accomplished and how they \
contributed to the final result. This is a progress summary of the plan itself, \
NOT a repetition of the detailed findings.

Rules:
1. Describe what each step did in 1-2 sentences (e.g. "Step 1 located core modules …")
2. End with 1-2 sentences on overall completion status and key takeaways
3. Keep the total length under 300 characters
4. Use the same language as the user's goal
5. Focus on the PROCESS (actions taken, files examined, analysis performed), \
not on restating the content of the results

Step results:
{step_results}

Output your plan summary directly:
"""


@dataclass
class ReflectionResult:
    """Result of a reflection pass."""

    satisfied: bool = True
    summary: str = ""
    plan_summary: str = ""
    revisions: list[str] = field(default_factory=list)


class Reflector:
    """Check execution results and optionally request revisions (max 2)."""

    def __init__(self, provider: LLMProvider, model: str | None = None, max_revisions: int = 2):
        self._provider = provider
        self._model = model
        self._max_revisions = max_revisions

    async def reflect(self, plan: TaskPlan) -> ReflectionResult:
        """Evaluate the plan results. Returns a ReflectionResult."""
        if plan.revision_count >= self._max_revisions:
            logger.info("Max revisions ({}) reached, accepting results", self._max_revisions)
            summary = await self._synthesize_results(plan)
            plan_summary = await self._generate_plan_summary(plan)
            return ReflectionResult(satisfied=True, summary=summary, plan_summary=plan_summary)

        step_results = self._format_step_results(plan)
        prompt = REFLECTOR_PROMPT.format(goal=plan.goal, step_results=step_results)

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please review the execution results."},
                ],
                model=self._model,
                temperature=0.1,
                max_tokens=2048,
            )
        except Exception:
            logger.debug("Reflector LLM call failed, accepting results")
            return ReflectionResult(satisfied=True, summary=self._compile_results(plan))

        result = self._parse_reflection(response.content, plan)

        # When satisfied, replace the brief reflector summary with a full synthesis
        if result.satisfied:
            result.summary = await self._synthesize_results(plan)
            result.plan_summary = await self._generate_plan_summary(plan)

        return result

    def _parse_reflection(self, content: str | None, plan: TaskPlan) -> ReflectionResult:
        """Parse the LLM reflection response."""
        if not content:
            return ReflectionResult(satisfied=True, summary=self._compile_results(plan))

        data = self._extract_json(content)
        if not data:
            return ReflectionResult(satisfied=True, summary=content)

        return ReflectionResult(
            satisfied=data.get("satisfied", True),
            summary=data.get("summary", self._compile_results(plan)),
            revisions=data.get("revisions", []),
        )

    async def _synthesize_results(self, plan: TaskPlan) -> str:
        """Use LLM to synthesize step results into a coherent response.

        Falls back to ``_compile_results`` if the synthesis call fails.
        """
        step_results = self._format_step_results(plan)
        prompt = SYNTHESIS_PROMPT.format(goal=plan.goal, step_results=step_results)

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please synthesize the results."},
                ],
                model=self._model,
                temperature=0.3,
                max_tokens=4096,
            )
            if response.content and response.finish_reason != "error":
                return response.content
        except Exception:
            logger.debug("Synthesis LLM call failed, falling back to compile")

        return self._compile_results(plan)

    async def _generate_plan_summary(self, plan: TaskPlan) -> str:
        """Generate a brief summary of the plan execution process.

        Describes what each step did and overall completion status,
        rather than restating the detailed findings.
        Falls back to a simple step-status listing on failure.
        """
        step_results = self._format_step_results(plan)
        prompt = PLAN_SUMMARY_PROMPT.format(goal=plan.goal, step_results=step_results)

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please summarize the plan execution."},
                ],
                model=self._model,
                temperature=0.2,
                max_tokens=512,
            )
            if response.content and response.finish_reason != "error":
                return response.content
        except Exception:
            logger.debug("Plan summary LLM call failed, falling back to step listing")

        # Fallback: simple step-status listing
        lines = []
        for step in plan.steps:
            status = "✓" if step.status == "done" else "✕"
            lines.append(f"{status} {step.description}")
        return "\n".join(lines)

    @staticmethod
    def _format_step_results(plan: TaskPlan) -> str:
        """Format step results for the reflector prompt."""
        lines: list[str] = []
        for step in plan.steps:
            status = step.status
            if step.result:
                lines.append(f"[{status}] {step.id} ({step.description}):\n{step.result}")
            elif step.error:
                lines.append(f"[{status}] {step.id} ({step.description}): ERROR: {step.error}")
            else:
                lines.append(f"[{status}] {step.id} ({step.description}): (no output)")
        return "\n\n".join(lines)

    @staticmethod
    def _compile_results(plan: TaskPlan) -> str:
        """Compile all step results into a final response."""
        parts: list[str] = []
        for step in plan.steps:
            if step.result:
                parts.append(step.result)
            elif step.error:
                parts.append(f"Step {step.id} failed: {step.error}")
        return "\n\n".join(parts) if parts else "Task completed but no results were produced."

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract JSON from LLM response."""
        import re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"\{[^{}]*\"satisfied\"[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None
