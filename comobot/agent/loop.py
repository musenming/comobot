"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
import weakref
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from comobot.agent.context import ContextBuilder
from comobot.agent.episodic.extractor import MemoryExtractor
from comobot.agent.episodic.injector import MemoryInjector
from comobot.agent.episodic.store import EpisodicMemoryStore
from comobot.agent.memory import MemoryStore
from comobot.agent.memory_backend import BuiltinBackend, MemoryBackend
from comobot.agent.memory_search import MemorySearchEngine
from comobot.agent.middleware.base import AgentContext
from comobot.agent.middleware.complexity import ComplexityRouter, EscalationSignal
from comobot.agent.planning.executor import TaskExecutor
from comobot.agent.planning.models import TaskPlan, TaskStep
from comobot.agent.planning.planner import TaskPlanner
from comobot.agent.planning.reflector import Reflector
from comobot.agent.reasoning import (
    PROMPT_BY_LEVEL,
    STALL_NUDGE,
    ReasoningContext,
    ReasoningLevel,
    classify_reasoning_level,
    detect_stall,
    extract_thought,
    strip_thought,
)
from comobot.agent.session_indexer import SessionIndexer
from comobot.agent.subagent import SubagentManager
from comobot.agent.tools.cron import CronTool
from comobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from comobot.agent.tools.knowhow_tools import KnowhowSaveTool, KnowhowSearchTool
from comobot.agent.tools.memory_tools import MemoryGetTool, MemorySearchTool
from comobot.agent.tools.message import MessageTool
from comobot.agent.tools.reflection.pipeline import ToolReflectionPipeline
from comobot.agent.tools.registry import ToolRegistry
from comobot.agent.tools.shell import ExecTool
from comobot.agent.tools.spawn import SpawnTool
from comobot.agent.tools.web import WebFetchTool, WebSearchTool
from comobot.agent.tools.wechat_login import WechatLoginTool
from comobot.bus.events import InboundMessage, OutboundMessage
from comobot.bus.queue import MessageBus
from comobot.providers.base import LLMProvider
from comobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from comobot.config.schema import (
        AgentProfilesConfig,
        ChannelsConfig,
        ContextOptimizerConfig,
        EpisodicMemoryConfig,
        ExecToolConfig,
        MemoryConfig,
        PlanningConfig,
        ReasoningConfig,
        ReflectionConfig,
    )
    from comobot.cron.service import CronService

# Instruction appended to each plan step's context so that step results
# can be parsed as structured JSON by downstream steps and the synthesizer.
_STEP_STRUCTURED_OUTPUT_INSTRUCTION = """

## Output Format
Provide your response as thorough and detailed as possible. At the very end of your \
response, append a JSON summary block fenced with ```json ... ```:
```json
{
  "summary": "1-2 sentence executive summary of what you found/did",
  "findings": ["key finding 1", "key finding 2", "..."],
  "actions_taken": ["action 1", "action 2"],
  "artifacts": ["file paths, URLs, or code snippets produced"]
}
```
The detailed text BEFORE the JSON block is the primary content — keep it comprehensive. \
The JSON block is supplementary metadata for downstream steps.
"""


def _try_parse_structured(text: str) -> dict | None:
    """Try to extract a structured JSON block from step output.

    Looks for a ```json ... ``` fenced block at the end of the text.
    Supports nested JSON via ``json_repair`` (already a project dependency).
    Returns the parsed dict or *None*.
    """
    if not text:
        return None

    # Strategy 1: match the last ```json ... ``` fenced block
    # Use a greedy match within the last fence to handle nested braces.
    match = re.search(r"```json\s*(\{.*\})\s*```\s*$", text, re.DOTALL)
    if match:
        raw = match.group(1)
        # Try standard json first (fast path)
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "summary" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback: json_repair for malformed JSON
        try:
            from json_repair import repair_json

            repaired = repair_json(raw, return_objects=True)
            if isinstance(repaired, dict) and "summary" in repaired:
                return repaired
        except Exception:
            pass

    # Strategy 2: look for a bare JSON object with "summary" key (no fence)
    match = re.search(r'\{[^{}]*"summary"[^{}]*\}', text[-2000:], re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "summary" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    return None


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        brave_api_key: str | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        memory_config: MemoryConfig | None = None,
        planning_config: PlanningConfig | None = None,
        episodic_config: EpisodicMemoryConfig | None = None,
        agent_profiles_config: AgentProfilesConfig | None = None,
        reasoning_config: ReasoningConfig | None = None,
        reflection_config: ReflectionConfig | None = None,
        context_optimizer_config: ContextOptimizerConfig | None = None,
    ):
        from comobot.config.schema import (
            AgentProfilesConfig,
            ContextOptimizerConfig,
            EpisodicMemoryConfig,
            ExecToolConfig,
            MemoryConfig,
            PlanningConfig,
            ReasoningConfig,
            ReflectionConfig,
        )

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.reasoning_effort = reasoning_effort
        self.brave_api_key = brave_api_key
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.memory_config = memory_config or MemoryConfig()

        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()

        # Tool reflection pipeline (wraps ToolRegistry)
        _rcfg = reflection_config or ReflectionConfig()
        self._reflection = ToolReflectionPipeline(
            registry=self.tools,
            enabled=_rcfg.enabled,
            max_retries=_rcfg.max_retries,
            max_consecutive_failures=_rcfg.max_consecutive_failures,
            max_duplicate_calls=_rcfg.max_duplicate_calls,
            cooldown_iterations=_rcfg.cooldown_iterations,
        )

        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=reasoning_effort,
            brave_api_key=brave_api_key,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._session_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._memory_flushed: set[str] = set()  # Session keys that have been flushed this cycle

        # Intervention hooks for Comobot Remote "descend" mode
        self._intervention_callbacks: dict[str, asyncio.Future] = {}
        self.orchestrator = None  # Optional WorkflowEngine for orchestrated flows
        self._db_session_manager = None  # Optional SQLiteSessionManager for DB sync

        # Initialize memory search engine and backend
        self._memory_engine = self._init_memory_engine()
        self._memory_backend: MemoryBackend | None = self._init_memory_backend()
        self._session_indexer = self._init_session_indexer()
        self.context = ContextBuilder(workspace, memory_engine=self._memory_engine)
        self._register_default_tools()

        # --- Agent v2 components ---
        self._planning_config = planning_config or PlanningConfig()
        self._reasoning_config = reasoning_config or ReasoningConfig()
        self._episodic_config = episodic_config or EpisodicMemoryConfig()
        self._agent_profiles_config = agent_profiles_config or AgentProfilesConfig()
        self._context_optimizer_config = context_optimizer_config or ContextOptimizerConfig()

        # Complexity router
        self._complexity_router: ComplexityRouter | None = None
        if self._planning_config.enabled:
            self._complexity_router = ComplexityRouter(
                escalation_tool_count=self._planning_config.escalation_tool_count,
                escalation_search_count=self._planning_config.escalation_search_count,
                escalation_error_count=self._planning_config.escalation_error_count,
                escalation_iteration_count=self._planning_config.escalation_iteration_count,
                llm_self_trigger=self._planning_config.llm_self_trigger,
                planning_enabled=self._planning_config.enabled,
            )

        # Planning engine
        self._planner: TaskPlanner | None = None
        self._reflector: Reflector | None = None
        if self._planning_config.enabled:
            self._planner = TaskPlanner(
                provider=provider,
                model=self.model,
                max_steps=self._planning_config.max_steps,
            )
            self._reflector = Reflector(
                provider=provider,
                model=self.model,
                max_revisions=self._planning_config.max_revisions,
            )

        # Episodic memory components (injector + extractor initialized lazily when DB is set)
        self._memory_injector: MemoryInjector | None = None
        self._memory_extractor: MemoryExtractor | None = None
        self._episodic_store: EpisodicMemoryStore | None = None
        if self._episodic_config.enabled:
            self._memory_injector = MemoryInjector(
                workspace=workspace,
                memory_engine=self._memory_engine,
                max_inject=self._episodic_config.max_inject,
            )
            self.context.set_memory_injector(self._memory_injector)

        # Workspace migration (creates episodic/, feedback/, agents/ directories)
        from comobot.agent.migration import migrate_workspace_v2

        migrate_workspace_v2(workspace)

    def set_db_session_manager(self, db_sm) -> None:
        """Set a SQLiteSessionManager for database sync of all session writes."""
        self._db_session_manager = db_sm

        # Initialize episodic store + extractor once DB is available
        if self._episodic_config.enabled and db_sm is not None:
            db = getattr(db_sm, "db", None) or getattr(db_sm, "_db", None)
            if db is not None:
                self._episodic_store = EpisodicMemoryStore(self.workspace, db)
                self._memory_extractor = MemoryExtractor(
                    store=self._episodic_store,
                    provider=self.provider,
                    model=self.model,
                    memory_engine=self._memory_engine,
                    confidence_threshold=self._episodic_config.confidence_threshold,
                )

    async def _sync_session_to_db(
        self,
        session: Session,
        new_messages: list[dict] | None = None,
        *,
        channel: str = "",
    ) -> None:
        """Incrementally sync new messages to SQLite database for API queries.

        Skips web channel sessions since ws.py already persists those directly.
        """
        if self._db_session_manager is None:
            return
        if channel == "web":
            return  # Web chat handler (ws.py) already writes to DB
        try:
            session_id = await self._db_session_manager.ensure_session(
                session.key, platform=channel
            )
            if new_messages:
                await self._db_session_manager.append_messages(session_id, new_messages)
        except Exception:
            logger.warning("DB session sync failed for {}", session.key, exc_info=True)

    def _init_memory_engine(self) -> MemorySearchEngine | None:
        """Initialize the memory search engine based on config."""
        cfg = self.memory_config.search
        if not cfg.enabled:
            return None

        try:
            engine = MemorySearchEngine(
                workspace=self.workspace,
                chunk_target_tokens=cfg.chunk_target_tokens,
                chunk_overlap_tokens=cfg.chunk_overlap_tokens,
                vector_weight=cfg.hybrid.vector_weight,
                text_weight=cfg.hybrid.text_weight,
                candidate_multiplier=cfg.hybrid.candidate_multiplier,
                temporal_decay_enabled=cfg.temporal_decay.enabled,
                half_life_days=cfg.temporal_decay.half_life_days,
                mmr_enabled=cfg.mmr.enabled,
                mmr_lambda=cfg.mmr.lambda_param,
                embedding_fn=self._build_embedding_fn(),
            )
            # Initial index build
            engine.reindex()
            return engine
        except Exception:
            logger.exception("Failed to initialize memory search engine")
            return None

    def _build_embedding_fn(self):
        """Build an embedding function from config. Returns None if unavailable."""
        cfg = self.memory_config.search
        if cfg.provider == "none":
            return None

        try:
            import litellm

            model = cfg.model

            def _embed(text: str) -> list[float] | None:
                try:
                    resp = litellm.embedding(model=model, input=[text])
                    return resp.data[0]["embedding"]
                except Exception:
                    return None

            # Test if embedding works
            test = _embed("test")
            if test:
                logger.info("Memory search: embedding via litellm/{}", model)
                return _embed
        except Exception:
            logger.debug("Embedding not available, using BM25-only search")

        return None

    def _init_memory_backend(self) -> MemoryBackend | None:
        """Initialize the memory backend based on config.

        Always wraps in FallbackBackend so QMD can be hot-swapped on/off
        from the frontend without restarting the gateway.
        """
        if not self._memory_engine:
            logger.info("Memory backend: disabled (search engine not available)")
            return None

        from comobot.agent.memory_backend import FallbackBackend
        from comobot.agent.qmd_backend import QMDBackend

        builtin = BuiltinBackend(self._memory_engine, self.workspace)
        qmd_cfg = self.memory_config.qmd
        qmd = QMDBackend(qmd_cfg, self.workspace)

        # Always create FallbackBackend for hot-swap support
        fb = FallbackBackend(qmd, builtin)

        backend_type = self.memory_config.backend
        qmd_wanted = backend_type == "qmd" or (backend_type == "auto" and qmd_cfg.enabled)

        if qmd_wanted:
            logger.info(
                "Memory backend: initializing QMD (mode={}, command={})",
                qmd_cfg.mode,
                qmd_cfg.command,
            )
        else:
            logger.info("Memory backend: builtin (BM25 + vector hybrid search), QMD hot-swap ready")

        return fb

    def _init_session_indexer(self) -> SessionIndexer | None:
        """Initialize the session indexer if configured."""
        cfg = self.memory_config.session_index
        if not cfg.enabled:
            return None
        sessions_dir = self.workspace / "sessions"
        if not sessions_dir.exists():
            return None
        try:
            return SessionIndexer(
                config=cfg,
                memory_engine=self._memory_engine,
                sessions_dir=sessions_dir,
                workspace=self.workspace,
            )
        except Exception:
            logger.exception("Failed to initialize session indexer")
            return None

    def _reindex_memory(self) -> None:
        """Reindex memory files (call after memory writes)."""
        if self._memory_engine:
            try:
                self._memory_engine.reindex()
            except Exception:
                logger.debug("Memory reindex failed")

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(
            ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            )
        )
        self.tools.register(WebSearchTool(api_key=self.brave_api_key, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(WechatLoginTool())
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        # Memory tools
        if self._memory_backend:
            self.tools.register(MemorySearchTool(backend=self._memory_backend))
        elif self._memory_engine:
            self.tools.register(MemorySearchTool(self._memory_engine))
        self.tools.register(MemoryGetTool(self.workspace))

        # Know-how tools (search only — save requires DB, registered when DB available)
        if self._memory_engine:
            self.tools.register(KnowhowSearchTool(self._memory_engine, None))

    def register_knowhow_tools(self, db) -> None:
        """Register Know-how tools that require DB access. Called by gateway when DB is available."""
        from comobot.knowhow.store import KnowhowStore

        store = KnowhowStore(self.workspace, db)
        # Update search tool with store (for usage tracking)
        if search_tool := self.tools.get("knowhow_search"):
            search_tool._store = store
        # Register save tool
        self.tools.register(KnowhowSaveTool(store))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from comobot.agent.tools.mcp import connect_mcp_servers

        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _extract_media_from_text(text: str) -> list[str]:
        """Extract local media file paths from markdown image references in text."""
        media_dir = Path.home() / ".comobot" / "media"
        paths: list[str] = []
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
            url = m.group(1)
            if url.startswith("/api/media/"):
                filename = url[len("/api/media/") :]
                fpath = (media_dir / filename).resolve()
                if str(fpath).startswith(str(media_dir.resolve())) and fpath.exists():
                    paths.append(str(fpath))
        return paths

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""

        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'

        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_tool_complete: Callable[[str, str, bool], None] | None = None,
        max_iterations: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
        tool_filter: list[str] | None = None,
        reasoning_level: ReasoningLevel | None = None,
    ) -> tuple[str | None, list[str], list[dict], list[str]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages, media).

        Args:
            on_tool_complete: Sync callback(tool_name, result, success) called after each tool.
                May raise EscalationSignal to interrupt the loop for plan mode.
            max_iterations: Override self.max_iterations for this run.
            model: Override self.model for this run.
            temperature: Override self.temperature for this run.
            tool_filter: If set, only expose tools whose names are in this list.
            reasoning_level: Override the auto-classified reasoning level for this run.
        """
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        collected_media: list[str] = []
        loop_max = max_iterations or self.max_iterations
        loop_model = model or self.model
        loop_temp = temperature if temperature is not None else self.temperature

        # ReAct reasoning state
        r_level = reasoning_level or ReasoningLevel.NONE
        r_cfg = self._reasoning_config
        recent_thoughts: list[str] = []

        # Build tool definitions, optionally filtered
        if tool_filter and "*" not in tool_filter:
            tool_defs = [
                d
                for d in self.tools.get_definitions()
                if d.get("function", {}).get("name") in tool_filter
            ]
        else:
            tool_defs = self.tools.get_definitions()

        while iteration < loop_max:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs,
                model=loop_model,
                temperature=loop_temp,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )

            if response.has_tool_calls:
                # --- ReAct: extract <thought> from intermediate responses ---
                thought = (
                    extract_thought(response.content) if r_level != ReasoningLevel.NONE else None
                )
                if thought:
                    logger.info("Thought [iter={}]: {}", iteration, thought[:300])
                    recent_thoughts.append(thought)
                    if on_progress:
                        await on_progress(thought, thinking=True)

                    # Stall detection (full mode only)
                    if (
                        r_level == ReasoningLevel.FULL
                        and r_cfg.stall_detection
                        and detect_stall(recent_thoughts, window=r_cfg.stall_window)
                    ):
                        logger.warning("Stall detected at iteration {}", iteration)
                        messages.append({"role": "user", "content": STALL_NUDGE})

                if on_progress:
                    clean = self._strip_think(response.content)
                    # Strip thought blocks from progress text to avoid duplication
                    clean = strip_thought(clean) if thought and clean else clean
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                # reasoning_content and thinking_blocks are NOT stored for tool-call
                # turns.  MiniMax's internal reasoning can hallucinate tool-call IDs that
                # never appeared in tool_calls — sending those artifacts back causes
                # "tool id XXX not found" errors on the next turn.
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self._reflection.execute(tool_call.name, tool_call.arguments)
                    success = not (isinstance(result, str) and result.startswith("Error"))
                    # Collect media references from tool results
                    if isinstance(result, str):
                        collected_media.extend(self._extract_media_from_text(result))
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                    # Notify tool-complete callback (may raise EscalationSignal)
                    if on_tool_complete:
                        on_tool_complete(
                            tool_call.name, result if isinstance(result, str) else "", success
                        )
            else:
                clean = self._strip_think(response.content)

                # Tier 3: LLM self-trigger — if the first response starts with [PLAN_MODE]
                if (
                    iteration == 1
                    and self._complexity_router
                    and self._complexity_router.check_llm_self_trigger(clean)
                ):
                    from comobot.agent.middleware.complexity import EscalationSignal

                    # Strip the [PLAN_MODE] tag from content
                    actual = clean.replace("[PLAN_MODE]", "", 1).strip() if clean else ""
                    raise EscalationSignal(
                        reason="LLM self-triggered plan mode",
                        completed_context=actual,
                    )

                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    error_type = response.error_type
                    logger.error("LLM error (type={}): {}", error_type, (clean or "")[:200])
                    if error_type == "content_safety":
                        final_content = (
                            "⚠️ 内容安全提示：AI 模型的内容安全过滤器拦截了此次请求。"
                            "请尝试调整您的输入或换个方式提问。\n\n"
                            "Content safety filter triggered. "
                            "Please try rephrasing your request."
                        )
                    elif error_type == "auth":
                        final_content = (
                            "⚠️ API 认证失败，请检查您的 API Key 配置。\n\n"
                            "API authentication failed. Please check your API key."
                        )
                    elif error_type == "context_length":
                        final_content = (
                            "⚠️ 对话上下文超出模型限制，请开始新的对话。\n\n"
                            "Conversation too long. Please start a new chat."
                        )
                    elif error_type == "rate_limit":
                        final_content = (
                            "⚠️ API 请求频率超限，已重试但仍失败，请稍后再试。\n\n"
                            "Rate limit exceeded after retries. Please try again later."
                        )
                    elif error_type == "network":
                        final_content = (
                            "⚠️ 网络连接异常，已重试但仍失败，请检查网络或稍后再试。\n\n"
                            "Network error after retries. Please check your connection."
                        )
                    else:
                        final_content = (
                            clean or "Sorry, I encountered an error calling the AI model."
                        )
                    break

                # Strip <thought> from final answer unless show_thinking is on
                if not r_cfg.show_thinking:
                    clean = strip_thought(clean) or clean

                messages = self.context.add_assistant_message(
                    messages,
                    clean,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= loop_max:
            logger.warning("Max iterations ({}) reached", loop_max)
            final_content = (
                f"I reached the maximum number of tool call iterations ({loop_max}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages, collected_media

    # ------------------------------------------------------------------
    # Plan-Execute-Reflect cycle for complex tasks
    # ------------------------------------------------------------------

    async def _planned_execute(
        self,
        message: str,
        session: Session,
        session_key: str,
        history: list[dict],
        *,
        bootstrap: str | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        channel: str = "",
        chat_id: str = "",
        ws_send: Callable[[dict], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict], list[str]]:
        """Execute a complex task via plan-execute-reflect cycle.

        Returns the same tuple as _run_agent_loop for API compatibility.
        """
        r_cfg = self._reasoning_config

        if not self._planner or not self._reflector:
            logger.warning("Planning engine not initialized, falling back to direct execution")
            fallback_prompt = PROMPT_BY_LEVEL.get(ReasoningLevel.FULL) if r_cfg.enabled else None
            msgs = self.context.build_messages(
                history=history,
                current_message=message,
                channel=channel,
                chat_id=chat_id,
                reasoning_prompt=fallback_prompt,
            )
            return await self._run_agent_loop(
                msgs,
                on_progress=on_progress,
                reasoning_level=ReasoningLevel.FULL if r_cfg.enabled else None,
            )

        # Build WS push callback so process messages reach the frontend in real-time
        async def _ws_notify(payload_json: str) -> None:
            if ws_send:
                await ws_send(json.loads(payload_json))

        # Push process message: planning phase
        if on_progress:
            await on_progress("Planning task decomposition...")

        # 1. Plan
        plan = await self._planner.plan(message, bootstrap=bootstrap)
        logger.info("Plan created: {} steps for '{}'", len(plan.steps), plan.goal[:80])

        # Push plan summary via process message
        await self._push_process(
            session,
            session_key,
            "plan_created",
            {
                "goal": plan.goal,
                "steps": [
                    {"id": s.id, "description": s.description, "agent_type": s.agent_type}
                    for s in plan.steps
                ],
            },
            ws_callback=_ws_notify,
        )

        # 2. Execute
        from comobot.agent.agents.profiles import get_profile

        all_tools_used: list[str] = []
        all_messages: list[dict] = []
        all_media: list[str] = []

        async def run_step(
            step: TaskStep, plan: TaskPlan, prior_results: dict[str, str]
        ) -> str | None:
            """Execute a single plan step via _run_agent_loop with appropriate profile."""
            profile = get_profile(step.agent_type)

            # Build step-specific context with structured prior results
            step_context = f"You are executing step {step.id} of a plan.\n"
            step_context += f"Overall goal: {plan.goal}\n"
            step_context += f"Your step: {step.description}\n"
            if step.dependencies and prior_results:
                step_context += "\n## Prior Step Results\n"
                for dep_id in step.dependencies:
                    if dep_id in prior_results:
                        prior = prior_results[dep_id]

                        # Handle failed dependency — surface the error clearly
                        if prior.startswith("[FAILED]"):
                            step_context += f"\n### {dep_id} (FAILED)\n"
                            step_context += f"{prior}\n"
                            step_context += (
                                "Note: this dependency failed. Adapt your approach accordingly.\n"
                            )
                            continue

                        parsed = _try_parse_structured(prior)
                        if parsed:
                            step_context += f"\n### {dep_id}\n"
                            step_context += f"**Summary**: {parsed.get('summary', '')}\n"

                            findings = parsed.get("findings", [])
                            if findings:
                                step_context += "\n**Key findings**:\n"
                                for finding in findings:
                                    step_context += f"- {finding}\n"

                            actions = parsed.get("actions_taken", [])
                            if actions:
                                step_context += "\n**Actions taken**:\n"
                                for action in actions:
                                    step_context += f"- {action}\n"

                            artifacts = parsed.get("artifacts", [])
                            if artifacts:
                                step_context += "\n**Artifacts** (files, URLs, code):\n"
                                for artifact in artifacts:
                                    step_context += f"- {artifact}\n"

                            # Dynamic detail truncation: scale with available content
                            # Short results (<4k): keep full; long results: cap at 6k
                            detail = parsed.get("detail", "")
                            if not detail:
                                # Extract detail from raw text (before the JSON fence)
                                fence_pos = prior.rfind("```json")
                                if fence_pos > 0:
                                    detail = prior[:fence_pos].strip()
                            if detail:
                                max_detail = 6000 if len(detail) > 4000 else len(detail)
                                step_context += f"\n**Detail**:\n{detail[:max_detail]}\n"
                        else:
                            # Unstructured result — keep more content than before
                            max_chars = 6000 if len(prior) > 4000 else len(prior)
                            step_context += f"\n### {dep_id}\n{prior[:max_chars]}\n"
                    else:
                        # Dependency not in prior_results — not yet executed
                        step_context += f"\n### {dep_id}\n(no results available)\n"

            step_context += _STEP_STRUCTURED_OUTPUT_INSTRUCTION

            # Reasoning: plan steps always get FULL level
            step_reasoning_prompt = (
                PROMPT_BY_LEVEL.get(ReasoningLevel.FULL) if r_cfg.enabled else None
            )

            step_messages = self.context.build_messages(
                history=[],
                current_message=step.description,
                channel=channel,
                chat_id=chat_id,
                plan_context=step_context,
                reasoning_prompt=step_reasoning_prompt,
            )

            # Push step progress
            await self._push_process(
                session,
                session_key,
                "plan_step",
                {
                    "step_id": step.id,
                    "description": step.description,
                    "status": "running",
                    "agent_type": step.agent_type,
                },
                ws_callback=_ws_notify,
            )

            tool_filter = profile.filter_tools(self.tools.tool_names)

            # Wrap on_progress to inject step_id for plan-step grouping
            _step_id = step.id

            async def _step_progress(
                content_text: str, *, tool_hint: bool = False, thinking: bool = False, **_kw: object
            ) -> None:
                if on_progress:
                    await on_progress(
                        content_text, tool_hint=tool_hint, step_id=_step_id, thinking=thinking
                    )

            content, tools, msgs, media = await self._run_agent_loop(
                step_messages,
                on_progress=_step_progress,
                max_iterations=profile.max_iterations,
                model=profile.model_override,
                temperature=profile.temperature,
                tool_filter=tool_filter if tool_filter != list(self.tools.tool_names) else None,
                reasoning_level=ReasoningLevel.FULL if r_cfg.enabled else None,
            )

            all_tools_used.extend(tools)
            all_messages.extend(msgs)
            all_media.extend(media)

            # Push step completion
            await self._push_process(
                session,
                session_key,
                "plan_step",
                {
                    "step_id": step.id,
                    "status": "done" if content else "failed",
                },
                ws_callback=_ws_notify,
            )

            # Cache structured result on the step to avoid re-parsing downstream
            if content:
                parsed = _try_parse_structured(content)
                if parsed:
                    step.structured_result = parsed

            return content

        async def on_plan_progress(plan: TaskPlan) -> None:
            await self._push_process(
                session,
                session_key,
                "plan_progress",
                {
                    "status": plan.status,
                    "completed": sum(1 for s in plan.steps if s.status == "done"),
                    "total": len(plan.steps),
                },
                ws_callback=_ws_notify,
            )

        executor = TaskExecutor(
            provider=self.provider,
            run_step_fn=run_step,
            on_progress=on_plan_progress,
        )
        plan = await executor.execute(plan)

        # 3. Reflect
        reflection = await self._reflector.reflect(plan)

        if (
            not reflection.satisfied
            and reflection.revisions
            and plan.revision_count < self._planning_config.max_revisions
        ):
            plan.revision_count += 1
            # Mark revision steps as pending
            for step in plan.steps:
                if step.id in reflection.revisions:
                    step.status = "pending"
                    step.result = None
                    step.error = None
            plan = await executor.execute(plan)
            reflection = await self._reflector.reflect(plan)

        plan.status = "done"
        plan.reflection = reflection.summary

        # The reflector now produces a synthesized summary via LLM that
        # coherently merges all step results.  Use it directly.
        final_answer = reflection.summary

        # Push completion with plan_summary (process-level summary),
        # not the full synthesis which is used as the main response.
        plan_summary = reflection.plan_summary or reflection.summary[:500]
        await self._push_process(
            session,
            session_key,
            "plan_complete",
            {
                "goal": plan.goal,
                "summary": plan_summary[:500],
            },
            ws_callback=_ws_notify,
        )

        return final_answer, all_tools_used, all_messages, all_media

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(
                    lambda t, k=msg.session_key: (
                        self._active_tasks.get(k, []) and self._active_tasks[k].remove(t)
                        if t in self._active_tasks.get(k, [])
                        else None
                    )
                )

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
            )
        )

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message, checking orchestrator first."""
        # Check if message matches an orchestrated workflow
        if self.orchestrator:
            try:
                workflow_id = await self.orchestrator.match_trigger(
                    msg.channel, msg.chat_id, msg.content
                )
                if workflow_id:
                    logger.info("Message matched workflow {}, routing to orchestrator", workflow_id)
                    trigger_data = {
                        "message": msg.content,
                        "sender_id": msg.sender_id,
                        "channel": msg.channel,
                        "chat_id": msg.chat_id,
                    }
                    await self.orchestrator.execute(workflow_id, trigger_data)
                    return
            except Exception:
                logger.exception("Orchestrator error, falling back to AgentLoop")

        # Per-session lock to allow concurrent processing of different sessions
        lock = self._session_locks.get(msg.session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[msg.session_key] = lock

        async with lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                    # Voice intent completion: push result back to Remote device
                    intent_id = (msg.metadata or {}).get("intent_id")
                    if intent_id:
                        asyncio.create_task(self._complete_voice_intent(intent_id, response, msg))
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata=msg.metadata or {},
                        )
                    )
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Sorry, I encountered an error.",
                    )
                )

    async def _complete_voice_intent(self, intent_id: str, response, msg) -> None:
        """Update voice_intent status to completed and notify the Remote device."""
        try:
            device_id = (msg.metadata or {}).get("device_id")
            result_text = (response.content or "")[:2000]

            # Update DB
            db = getattr(self._db_session_manager, "db", None) if self._db_session_manager else None
            if db:
                result_json = json.dumps({"content": result_text}, ensure_ascii=False)
                await db.execute(
                    "UPDATE voice_intents SET status = 'completed', result = ?, "
                    "session_key = ?, updated_at = datetime('now') WHERE id = ?",
                    (result_json, msg.session_key, intent_id),
                )

            # Push to Remote device via encrypted WS
            if device_id:
                from comobot.api.routes.ws_remote import get_remote_manager

                remote_mgr = get_remote_manager()
                await remote_mgr.send_encrypted(
                    device_id,
                    {
                        "t": "intent_update",
                        "intent_id": intent_id,
                        "status": "completed",
                        "result": result_text,
                        "session_key": msg.session_key,
                    },
                )
        except Exception as e:
            logger.warning("Failed to complete voice intent {}: {}", intent_id, e)

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        ws_send: Callable[[dict], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (
                msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            )
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                channel=channel,
                chat_id=chat_id,
            )
            final_content, _, all_msgs, _ = await self._run_agent_loop(messages)
            prev_count = len(session.messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            new_msgs = session.messages[prev_count:]
            self.sessions.save(session)
            await self._sync_session_to_db(session, new_msgs, channel=channel)
            await self._broadcast_session_messages(key, new_msgs)
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=final_content or "Background task completed.",
            )

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated :]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)

            session.clear()
            self.sessions.save(session)
            await self._sync_session_to_db(session, channel=msg.channel)
            self.sessions.invalidate(session.key)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="New session started."
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="🤖 comobot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands",
            )

        unconsolidated = len(session.messages) - session.last_consolidated

        # Pre-compaction memory flush: save durable memories before consolidation
        flush_cfg = self.memory_config.flush
        if (
            flush_cfg.enabled
            and session.key not in self._memory_flushed
            and unconsolidated >= int(self.memory_window * flush_cfg.soft_threshold_ratio)
            and unconsolidated < self.memory_window
        ):
            self._memory_flushed.add(session.key)
            try:
                await MemoryStore(self.workspace).memory_flush(session, self.provider, self.model)
                self._reindex_memory()
            except Exception:
                logger.debug("Memory flush failed, continuing")

        if unconsolidated >= self.memory_window and session.key not in self._consolidating:
            self._consolidating.add(session.key)
            self._memory_flushed.discard(session.key)  # Reset flush for next cycle
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                        self._reindex_memory()  # Reindex after consolidation writes
                finally:
                    self._consolidating.discard(session.key)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=self.memory_window)

        # Determine if planning self-trigger should be active
        plan_self_trigger = self._planning_config.enabled and self._planning_config.llm_self_trigger

        # Check for explicit plan mode prefix (Tier 1)
        user_content = msg.content
        force_plan = False
        explicit_trigger = False
        for prefix in ("/plan ", "/think ", "/deep "):
            if user_content.startswith(prefix):
                user_content = user_content[len(prefix) :]
                force_plan = True
                explicit_trigger = prefix.strip().lstrip("/") in ("think", "deep")
                break

        # Classify reasoning level (zero LLM cost)
        r_cfg = self._reasoning_config
        if r_cfg.enabled:
            r_ctx = ReasoningContext(
                in_plan_step=False,
                explicit_trigger=explicit_trigger,
                escalated=False,
            )
            reasoning_level = classify_reasoning_level(
                user_content, history, r_ctx, default_level=r_cfg.default_level
            )
        else:
            reasoning_level = ReasoningLevel.NONE
        reasoning_prompt = PROMPT_BY_LEVEL.get(reasoning_level) or None

        initial_messages = self.context.build_messages(
            history=history,
            current_message=user_content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            plan_self_trigger=plan_self_trigger and not force_plan,
            reasoning_prompt=reasoning_prompt,
            model=self.model,
            optimizer_config=self._context_optimizer_config,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False, **_kw: Any) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        progress_fn = on_progress or _bus_progress

        if force_plan and self._planner:
            # Explicit plan mode: go directly to plan-execute-reflect
            logger.info("Explicit plan mode for {}", key)
            final_content, _, all_msgs, tool_media = await self._planned_execute(
                user_content,
                session,
                key,
                history,
                on_progress=progress_fn,
                channel=msg.channel,
                chat_id=msg.chat_id,
                ws_send=ws_send,
            )
        else:
            # Normal path: run agent loop with escalation monitoring
            on_tool_cb = None
            if self._complexity_router and self._planning_config.enabled:
                _, on_tool_cb = self._complexity_router.create_tool_callback(
                    AgentContext(
                        message_content=user_content,
                        session_key=key,
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        session=session,
                    ),
                    initial_messages,
                )

            try:
                final_content, _, all_msgs, tool_media = await self._run_agent_loop(
                    initial_messages,
                    on_progress=progress_fn,
                    on_tool_complete=on_tool_cb,
                    reasoning_level=reasoning_level,
                )
            except EscalationSignal as esc:
                # Runtime escalation: switch to plan mode with prior context
                logger.info("Escalation to plan mode: {}", esc.reason)
                if progress_fn:
                    await progress_fn(
                        f"Detected complex task ({esc.reason}), switching to planning mode..."
                    )
                final_content, _, all_msgs, tool_media = await self._planned_execute(
                    user_content,
                    session,
                    key,
                    history,
                    bootstrap=esc.completed_context,
                    on_progress=progress_fn,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    ws_send=ws_send,
                )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        prev_count = len(session.messages)
        self._save_turn(session, all_msgs, 1 + len(history))
        new_msgs = session.messages[prev_count:]
        self.sessions.save(session)
        await self._sync_session_to_db(session, new_msgs, channel=msg.channel)

        # Session transcript indexing (debounced, non-blocking)
        if self._session_indexer:
            try:
                await self._session_indexer.check_and_index()
            except Exception:
                logger.debug("Session indexing failed")

        # Episodic memory extraction (async, non-blocking)
        if self._memory_extractor and self._episodic_config.auto_extract and new_msgs:

            async def _extract_memories():
                try:
                    await self._memory_extractor.extract(
                        new_msgs,
                        source_session=key,
                        source_channel=msg.channel,
                    )
                    self._reindex_memory()
                except Exception:
                    logger.debug("Episodic memory extraction failed")

            _etask = asyncio.create_task(_extract_memories())
            self._consolidation_tasks.add(_etask)
            _etask.add_done_callback(self._consolidation_tasks.discard)

        # Broadcast new messages to WebSocket session listeners.
        # Skip for web channel — ws_chat already sends responses via /ws/chat.
        if msg.channel != "web":
            await self._broadcast_session_messages(key, new_msgs)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool):
            if mt._sent_in_turn:
                return None
            # Mirror cross-channel messages back to web UI
            if msg.channel == "web" and mt._cross_channel_messages:
                parts = []
                for xmsg in mt._cross_channel_messages:
                    parts.append(xmsg["content"])
                    for media_path in xmsg.get("media", []):
                        fname = media_path.rsplit("/", 1)[-1] if "/" in media_path else media_path
                        parts.append(f"![{fname}](/api/media/{fname})")
                mirrored = "\n\n".join(parts)
                # Prepend mirrored content to the final response
                if final_content:
                    final_content = mirrored + "\n\n" + final_content
                else:
                    final_content = mirrored

        # Also extract media from final response text
        if final_content:
            tool_media.extend(self._extract_media_from_text(final_content))
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_media: list[str] = []
        for p in tool_media:
            if p not in seen:
                seen.add(p)
                unique_media.append(p)

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            media=unique_media,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime

        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "process":
                continue  # process messages are written by _push_process(), skip here
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if (
                role == "tool"
                and isinstance(content, str)
                and len(content) > self._TOOL_RESULT_MAX_CHARS
            ):
                entry["content"] = content[: self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(
                    ContextBuilder._RUNTIME_CONTEXT_TAG
                ):
                    # Strip the runtime-context prefix, keep only the user text.
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = []
                    for c in content:
                        if (
                            c.get("type") == "text"
                            and isinstance(c.get("text"), str)
                            and c["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG)
                        ):
                            continue  # Strip runtime context from multimodal messages
                        if c.get("type") == "image_url" and c.get("image_url", {}).get(
                            "url", ""
                        ).startswith("data:image/"):
                            filtered.append({"type": "text", "text": "[image]"})
                        else:
                            filtered.append(c)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _broadcast_session_messages(self, session_key: str, messages: list[dict]) -> None:
        """Broadcast new messages to WebSocket session listeners."""
        try:
            from comobot.api.routes.ws import manager as ws_manager

            last_content = ""
            for m in messages:
                role = m.get("role")
                content = m.get("content", "")

                # Process messages: broadcast as "process" event
                if role == "process":
                    process_type = m.get("tool_calls", "")
                    try:
                        _ = json.loads(content) if isinstance(content, str) else content
                    except (json.JSONDecodeError, TypeError):
                        pass
                    await ws_manager.broadcast_session_event(
                        {
                            "event": "new_message",
                            "session_key": session_key,
                            "message": {
                                "role": "process",
                                "process_type": process_type,
                                "content": str(content)[:500],
                                "created_at": m.get("timestamp", ""),
                            },
                        }
                    )
                    continue

                if role not in ("user", "assistant"):
                    continue  # Only broadcast user/assistant for web UI
                if role == "assistant" and not content:
                    continue
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if c.get("type") == "text"
                    )
                if not content:
                    continue
                await ws_manager.broadcast_session_event(
                    {
                        "event": "new_message",
                        "session_key": session_key,
                        "message": {
                            "role": role,
                            "content": str(content)[:500],
                            "created_at": m.get("timestamp", ""),
                        },
                    }
                )
                last_content = str(content)[:100]

            # Broadcast session metadata update (title from key, summary from last message)
            if last_content:
                parts = session_key.split(":", 1)
                title = parts[1][:30] if len(parts) == 2 else session_key[:30]
                await ws_manager.broadcast_session_update(
                    session_key, title=title, summary=last_content
                )
        except Exception:
            logger.debug("Session WS broadcast skipped (no API running)")

    async def _consolidate_memory(self, session, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session,
            self.provider,
            self.model,
            archive_all=archive_all,
            memory_window=self.memory_window,
        )

    # --- Process message persistence (Agent v2) ---

    async def _push_process(
        self,
        session: Session,
        session_key: str,
        process_type: str,
        data: dict,
        *,
        ws_callback: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        """Push a process message: write to DB + optional WS real-time push.

        Process messages (role="process") persist alongside user/assistant messages
        so they survive page refreshes.  The ``tool_calls`` field stores the
        ``process_type`` string for fast filtering.
        """
        from datetime import datetime

        content = json.dumps(data, ensure_ascii=False)
        msg: dict = {
            "role": "process",
            "content": content,
            "tool_calls": process_type,
            "timestamp": datetime.now().isoformat(),
        }

        # Append to in-memory session history
        session.messages.append(msg)

        # Persist to SQLite via session manager
        if self._db_session_manager:
            try:
                session_id = await self._db_session_manager.ensure_session(session_key)
                await self._db_session_manager.append_messages(session_id, [msg])
            except Exception:
                logger.debug("Process message DB write failed for {}", session_key)

        # Real-time WS push (if callback provided by caller)
        if ws_callback:
            try:
                await ws_callback(
                    json.dumps(
                        {
                            "type": "process",
                            "session_key": session_key,
                            "process_type": process_type,
                            **data,
                        },
                        ensure_ascii=False,
                    )
                )
            except Exception:
                logger.debug("Process message WS push failed for {}", session_key)

    # --- Intervention API for Comobot Remote "descend" mode ---

    async def request_intervention(
        self, session_key: str, draft: str, timeout: float = 30.0
    ) -> tuple[str, str]:
        """Request mobile intervention for a draft response.

        Returns (action, content) where action is 'approve', 'edit', or 'reject'.
        Times out after `timeout` seconds and auto-approves.
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._intervention_callbacks[session_key] = future
        try:
            action, content = await asyncio.wait_for(future, timeout=timeout)
            return action, content
        except asyncio.TimeoutError:
            logger.debug("Intervention timed out for {}, auto-approving", session_key)
            return "approve", draft
        finally:
            self._intervention_callbacks.pop(session_key, None)

    def register_intervention_response(self, session_key: str, action: str, content: str) -> None:
        """Called by WS handler when mobile sends an intervention response."""
        future = self._intervention_callbacks.get(session_key)
        if future and not future.done():
            future.set_result((action, content))
            logger.debug("Intervention response for {}: {}", session_key, action)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        ws_send: Callable[[dict], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress, ws_send=ws_send
        )
        return response.content if response else ""
