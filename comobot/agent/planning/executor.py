"""Task executor: runs plan steps with topological ordering and parallel execution."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

from comobot.agent.planning.models import TaskPlan, TaskStep

if TYPE_CHECKING:
    from comobot.providers.base import LLMProvider


class TaskExecutor:
    """Execute a TaskPlan by running steps in topological order.

    Steps at the same topological level (no mutual dependencies) run concurrently.
    Each step is executed via `run_step_fn`, a callback that invokes the agent loop
    with the appropriate profile/tools for the step's `agent_type`.
    """

    def __init__(
        self,
        provider: LLMProvider,
        run_step_fn: Callable[[TaskStep, TaskPlan, dict[str, str]], Awaitable[str | None]],
        on_progress: Callable[[TaskPlan], Awaitable[None]] | None = None,
    ):
        self._provider = provider
        self._run_step = run_step_fn
        self._on_progress = on_progress

    async def execute(self, plan: TaskPlan) -> TaskPlan:
        """Execute the plan. Returns the updated plan with results filled in."""
        plan.status = "executing"
        levels = self._topological_levels(plan.steps)

        # Seed with results from steps already done (e.g. from a prior execution
        # round before revision).  Without this, revised steps that depend on
        # non-revised steps would receive empty prior_results.
        completed_results: dict[str, str] = {}
        for s in plan.steps:
            if s.status == "done" and s.result:
                completed_results[s.id] = s.result
            elif s.status == "failed" and s.error:
                completed_results[s.id] = f"[FAILED] {s.error}"

        for level in levels:
            runnable = [s for s in level if s.status == "pending"]
            if not runnable:
                continue

            for s in runnable:
                s.status = "running"

            tasks = [self._execute_one(step, plan, completed_results) for step in runnable]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(runnable, results):
                if isinstance(result, BaseException):
                    step.status = "failed"
                    step.error = str(result)
                    completed_results[step.id] = f"[FAILED] {step.error}"
                    logger.warning("Step {} failed: {}", step.id, step.error[:200])
                else:
                    step.status = "done"
                    step.result = result
                    completed_results[step.id] = result or ""

            if self._on_progress:
                try:
                    await self._on_progress(plan)
                except Exception:
                    logger.debug("Progress callback failed")

        plan.status = "reflecting" if plan.is_complete else "failed"
        return plan

    async def _execute_one(
        self, step: TaskStep, plan: TaskPlan, prior_results: dict[str, str]
    ) -> str | None:
        """Execute a single step."""
        return await self._run_step(step, plan, prior_results)

    @staticmethod
    def _topological_levels(steps: list[TaskStep]) -> list[list[TaskStep]]:
        """Group steps into topological levels for parallel execution.

        Steps with no unsatisfied dependencies are at level 0, etc.
        """
        step_map = {s.id: s for s in steps}
        in_degree: dict[str, int] = {s.id: 0 for s in steps}
        dependents: dict[str, list[str]] = defaultdict(list)

        for s in steps:
            for dep_id in s.dependencies:
                if dep_id in step_map:
                    in_degree[s.id] += 1
                    dependents[dep_id].append(s.id)

        levels: list[list[TaskStep]] = []
        remaining = set(in_degree.keys())

        while remaining:
            # Find all steps with no remaining dependencies
            ready = [sid for sid in remaining if in_degree[sid] == 0]
            if not ready:
                # Circular dependency — force remaining into one level
                logger.warning("Circular dependency detected, forcing remaining steps")
                levels.append([step_map[sid] for sid in remaining])
                break
            level = [step_map[sid] for sid in ready]
            levels.append(level)
            for sid in ready:
                remaining.remove(sid)
                for dep_sid in dependents.get(sid, []):
                    in_degree[dep_sid] -= 1

        return levels
