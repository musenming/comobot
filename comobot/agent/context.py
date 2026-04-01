"""Context builder for assembling agent prompts."""

from __future__ import annotations

import base64
import mimetypes
import platform
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from comobot.agent.context_optimizer import (
    HistoryOptimizer,
    TaskClassifier,
    TaskType,
    get_profile,
    safety_trim_messages,
)
from comobot.agent.memory import MemoryStore
from comobot.agent.skills import SkillsLoader

if TYPE_CHECKING:
    from comobot.agent.episodic.injector import MemoryInjector
    from comobot.agent.memory_search import MemorySearchEngine
    from comobot.config.schema import ContextOptimizerConfig

PLAN_SELF_TRIGGER_INSTRUCTION = """
# Plan Mode Self-Trigger

If you determine that the current task requires multi-step execution (involving
multiple tool collaborations, gathering information from multiple sources, or
scenarios where research is needed before execution), output [PLAN_MODE] at the
very beginning of your response. The system will automatically switch to planning
mode to decompose the task for you.
"""

# Approximate characters per token for budget estimation.
_CHARS_PER_TOKEN = 3.5
# Default max system prompt tokens (can be overridden via config).
_DEFAULT_MAX_SYSTEM_TOKENS = 12000


@dataclass
class _ContextLayer:
    """A single layer of the system prompt with priority metadata."""

    name: str
    content: str
    priority: float  # 0.0 = droppable, 1.0 = must keep


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace: Path, memory_engine: MemorySearchEngine | None = None):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
        self._memory_engine = memory_engine
        self._memory_injector: MemoryInjector | None = None

    def set_memory_injector(self, injector: MemoryInjector) -> None:
        """Set the episodic/feedback memory injector (initialized by AgentLoop)."""
        self._memory_injector = injector

    def build_system_prompt(
        self,
        skill_names: list[str] | None = None,
        user_message: str | None = None,
        plan_context: str | None = None,
        plan_self_trigger: bool = False,
        reasoning_prompt: str | None = None,
        max_system_tokens: int | None = None,
        task_type: TaskType | None = None,
    ) -> str:
        """Build the system prompt from identity, bootstrap files, memory, knowhow, and skills.

        Layer order (inspired by Claude Code context engineering):
        1. Identity Layer         (priority=1.0, never dropped)
        2. Soul/Bootstrap Layer   (priority=0.9)
        3. Feedback Layer         (priority=1.0, never dropped)
        4. Memory Layer           (priority=dynamic, based on relevance)
        5. Know-how Layer         (priority=dynamic, based on relevance)
        6. Reasoning Layer        (priority=0.8)
        7. Plan Layer             (priority=1.0 when present)
        8. Tools & Skills Layer   (priority=dynamic)

        When *task_type* is provided, layer priorities are adjusted according to
        the corresponding :class:`ContextProfile`.

        When the combined prompt exceeds ``max_system_tokens`` the lowest-
        priority layers are trimmed first.
        """
        profile = get_profile(task_type) if task_type else None
        layers: list[_ContextLayer] = []

        # 1. Identity (always kept)
        layers.append(_ContextLayer("identity", self._get_identity(), priority=1.0))

        # 2. Bootstrap (SOUL.md, AGENTS.md, USER.md, TOOLS.md, IDENTITY.md)
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            layers.append(_ContextLayer("bootstrap", bootstrap, priority=0.9))

        # 3 & 4. Feedback + Episodic memory injection (via MemoryInjector)
        if self._memory_injector and user_message:
            injected_parts = self._memory_injector.inject(user_message)
            for part in injected_parts:
                # Feedback layers are high-priority; episodic are relevance-scored
                is_feedback = "Preferences" in part or "Feedback" in part
                layers.append(
                    _ContextLayer(
                        "feedback" if is_feedback else "episodic",
                        part,
                        priority=1.0 if is_feedback else 0.6,
                    )
                )

        # 4 (continued). Long-term memory (MEMORY.md + daily logs)
        memory = self.memory.get_memory_context()
        if memory:
            relevance = self._estimate_relevance(memory, user_message) if user_message else 0.5
            layers.append(_ContextLayer("memory", f"# Memory\n\n{memory}", priority=relevance))

        # 5. Know-how retrieval
        if user_message and self._memory_engine:
            knowhow_text = self._retrieve_knowhow(user_message)
            if knowhow_text:
                relevance = self._estimate_relevance(knowhow_text, user_message)
                layers.append(
                    _ContextLayer(
                        "knowhow",
                        f"# Relevant Experience (Know-how)\n\n{knowhow_text}",
                        priority=relevance,
                    )
                )

        # 6. Reasoning layer (ReAct instructions)
        if reasoning_prompt:
            layers.append(_ContextLayer("reasoning", reasoning_prompt, priority=0.8))

        # 7. Plan layer (only when executing a plan — always kept)
        if plan_context:
            layers.append(
                _ContextLayer("plan", f"# Current Task Plan\n\n{plan_context}", priority=1.0)
            )

        # LLM self-trigger instruction
        if plan_self_trigger:
            layers.append(
                _ContextLayer("plan_trigger", PLAN_SELF_TRIGGER_INSTRUCTION, priority=0.5)
            )

        # 8. Skills
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                layers.append(
                    _ContextLayer(
                        "active_skills",
                        f"# Active Skills\n\n{always_content}",
                        priority=0.7,
                    )
                )

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            layers.append(
                _ContextLayer(
                    "skills_summary",
                    f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""",
                    priority=0.5,
                )
            )

        # Apply task-type-driven priority adjustments
        if profile and profile.priority_overrides:
            for layer in layers:
                if layer.name in profile.priority_overrides:
                    override = profile.priority_overrides[layer.name]
                    # Only raise priority, never lower below the original
                    # (except for explicit low overrides like 0.0/0.3)
                    if override <= 0.3 or override > layer.priority:
                        layer.priority = override

            if task_type:
                logger.debug("Task type: {}, adjusted layer priorities", task_type.value)

        # Budget trimming: drop lowest-priority layers if over budget
        budget = max_system_tokens or _DEFAULT_MAX_SYSTEM_TOKENS
        layers = self._budget_trim(layers, budget)

        return "\n\n---\n\n".join(layer.content for layer in layers)

    @staticmethod
    def _estimate_relevance(content: str, user_message: str) -> float:
        """Estimate relevance between content and user_message via term overlap.

        Returns a value in [0.3, 0.9] — never drops below 0.3 to keep a
        minimum chance of inclusion.
        """
        if not user_message or not content:
            return 0.5

        # Tokenize: split on non-alphanumeric (works for CJK and Latin)
        def _tokens(text: str) -> set[str]:
            # For CJK, also split into character bigrams
            words = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
            # Add CJK character bigrams
            cjk = re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]+", text)
            for run in cjk:
                for i in range(len(run) - 1):
                    words.add(run[i : i + 2])
                if run:
                    words.add(run)
            return words

        query_tokens = _tokens(user_message)
        content_tokens = _tokens(content[:3000])  # cap for speed

        if not query_tokens:
            return 0.5

        overlap = query_tokens & content_tokens
        jaccard = len(overlap) / max(len(query_tokens | content_tokens), 1)

        # Map jaccard (typically 0.0–0.3) to priority range [0.3, 0.9]
        return min(0.9, 0.3 + jaccard * 2.0)

    @staticmethod
    def _budget_trim(layers: list[_ContextLayer], max_tokens: int) -> list[_ContextLayer]:
        """Drop lowest-priority layers until total fits within token budget."""

        def _est_tokens(text: str) -> int:
            return max(1, int(len(text) / _CHARS_PER_TOKEN))

        total = sum(_est_tokens(lay.content) for lay in layers)
        if total <= max_tokens:
            return layers

        # Sort by priority ascending (lowest first) for trimming candidates
        # but preserve original order in the final output
        indexed = list(enumerate(layers))
        trimmable = sorted(
            [(i, lay) for i, lay in indexed if lay.priority < 1.0],
            key=lambda x: x[1].priority,
        )

        removed: set[int] = set()
        for idx, layer in trimmable:
            if total <= max_tokens:
                break
            total -= _est_tokens(layer.content)
            removed.add(idx)

        return [lay for i, lay in indexed if i not in removed]

    def _retrieve_knowhow(self, user_message: str) -> str:
        """Retrieve relevant Know-how entries for the current user message."""
        if not self._memory_engine:
            return ""
        try:
            chunks = self._memory_engine.search(user_message, max_results=3, file_filter="knowhow/")
            # Filter by score threshold
            chunks = [c for c in chunks if c.score >= 0.3]
            if not chunks:
                return ""
            return self._format_knowhow(chunks)
        except Exception:
            return ""

    @staticmethod
    def _format_knowhow(chunks: list) -> str:
        """Format Know-how search results as Markdown."""
        sections = []
        for chunk in chunks:
            sections.append(
                f"## {chunk.file_path}\n(relevance: {chunk.score:.2f})\n\n{chunk.content}"
            )
        return "\n\n".join(sections)

    def _get_identity(self) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# comobot 🤖

You are comobot, a helpful AI assistant.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md (write important facts here)
- Daily logs: {workspace_path}/memory/YYYY-MM-DD.md (daily notes, auto-loaded for today + yesterday)
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## Memory
- Use `memory_search` to recall past conversations, decisions, and context.
- Use `memory_get` to read a specific memory file after search.
- Write important facts to MEMORY.md using edit_file or write_file.
- Day-to-day notes go to memory/YYYY-MM-DD.md (today's date).
- If someone says "remember this," write it to a memory file immediately.

## comobot Guidelines
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.

Reply directly with text for conversations. Only use the 'message' tool to send to a specific chat channel."""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
        """Build untrusted runtime metadata block for injection before the user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        plan_context: str | None = None,
        plan_self_trigger: bool = False,
        reasoning_prompt: str | None = None,
        model: str | None = None,
        optimizer_config: ContextOptimizerConfig | None = None,
    ) -> list[dict[str, Any]]:
        """Build the complete message list for an LLM call.

        When *optimizer_config* is provided and enabled, applies:
        1. Task classification to determine context composition
        2. History optimization (relevance scoring + progressive compression)
        3. Token safety trimming (only when approaching model limit)
        """
        # Task classification
        task_type: TaskType | None = None
        if optimizer_config and optimizer_config.enabled and optimizer_config.task_classification:
            task_type = TaskClassifier.classify(current_message, history)
            logger.debug("Classified task type: {}", task_type.value if task_type else "none")

        # History optimization
        optimized_history = history
        if (
            optimizer_config
            and optimizer_config.enabled
            and optimizer_config.history_optimization
            and task_type
        ):
            optimizer = HistoryOptimizer()
            optimized_history = optimizer.optimize(history, current_message, task_type)
            if len(optimized_history) != len(history):
                logger.debug(
                    "History optimized: {} messages -> {} messages",
                    len(history),
                    len(optimized_history),
                )

        runtime_ctx = self._build_runtime_context(channel, chat_id)
        user_content = self._build_user_content(current_message, media)

        # Merge runtime context and user content into a single user message
        # to avoid consecutive same-role messages that some providers reject.
        if isinstance(user_content, str):
            merged = f"{runtime_ctx}\n\n{user_content}"
        else:
            merged = [{"type": "text", "text": runtime_ctx}] + user_content

        messages = [
            {
                "role": "system",
                "content": self.build_system_prompt(
                    skill_names,
                    user_message=current_message,
                    plan_context=plan_context,
                    plan_self_trigger=plan_self_trigger,
                    reasoning_prompt=reasoning_prompt,
                    task_type=task_type,
                ),
            },
            *optimized_history,
            {"role": "user", "content": merged},
        ]

        # Token safety net — only trims when approaching model context limit
        if optimizer_config and optimizer_config.enabled and optimizer_config.safety_trim:
            messages = safety_trim_messages(messages, model)

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        """Add a tool result to the message list."""
        messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result}
        )
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Add an assistant message to the message list."""
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        if thinking_blocks:
            msg["thinking_blocks"] = thinking_blocks
        messages.append(msg)
        return messages
