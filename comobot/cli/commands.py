"""CLI commands for comobot."""

import asyncio
import io
import os
import select
import signal
import subprocess
import sys
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from comobot import __logo__, __version__
from comobot.config.schema import Config
from comobot.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="comobot",
    help=f"{__logo__} comobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}


def _get_pid_file() -> Path:
    """Return the path to the gateway PID file."""
    from comobot.config.loader import get_data_dir

    return get_data_dir() / "gateway.pid"


def _get_log_dir() -> Path:
    """Return the path to the logs directory (~/.comobot/logs/)."""
    from comobot.config.loader import get_data_dir

    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _write_pid_file() -> None:
    """Write the current process PID to the PID file."""
    pid_file = _get_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))


def _remove_pid_file() -> None:
    """Remove the PID file if it exists."""
    pid_file = _get_pid_file()
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)


def _read_pid() -> int | None:
    """Read the gateway PID from the PID file. Returns None if not found or stale."""
    pid_file = _get_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is still running
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        _remove_pid_file()
        return None


def _stop_gateway(port: int = 18790) -> bool:
    """Stop the running gateway process. Returns True if a process was stopped."""
    stopped = False

    # Try PID file first
    pid = _read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            console.print(f"  [green]✓[/green] Sent SIGTERM to gateway (pid={pid})")
            stopped = True
        except ProcessLookupError:
            pass
        _remove_pid_file()

    # Also try by port as fallback
    my_pid = str(os.getpid())
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
        )
        for p in result.stdout.strip().splitlines():
            p = p.strip()
            if p and p != my_pid:
                subprocess.run(["kill", p], capture_output=True)
                if not stopped:
                    console.print(f"  [green]✓[/green] Stopped process on port {port} (pid={p})")
                stopped = True
    except FileNotFoundError:
        pass

    return stopped


# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".comobot" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} comobot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} comobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """comobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize comobot configuration and workspace."""
    from comobot.config.loader import get_config_path, load_config, save_config
    from comobot.config.schema import Config
    from comobot.utils.helpers import get_workspace_path

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print(
            "  [bold]N[/bold] = refresh config, keeping existing values and adding new fields"
        )
        if typer.confirm("Overwrite?"):
            config = Config()
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config()
            save_config(config)
            console.print(
                f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)"
            )
    else:
        save_config(Config())
        console.print(f"[green]✓[/green] Created config at {config_path}")

    # Create workspace
    workspace = get_workspace_path()

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace}")

    sync_workspace_templates(workspace)

    console.print(f"\n{__logo__} comobot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.comobot/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print('  2. Chat: [cyan]comobot agent -m "Hello!"[/cyan]')
    console.print(
        "\n[dim]Want Telegram/WhatsApp? See: https://github.com/musenming/comobot#-chat-apps[/dim]"
    )


def _make_provider(config: Config, require_key: bool = True):
    """Create the appropriate LLM provider from config."""
    from comobot.providers.custom_provider import CustomProvider
    from comobot.providers.litellm_provider import LiteLLMProvider
    from comobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from comobot.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    key_missing = (
        not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth)
    )
    if key_missing:
        if require_key:
            console.print("[red]Error: No API key configured.[/red]")
            console.print("Set one in ~/.comobot/config.json under providers section")
            raise typer.Exit(1)
        # Gateway mode: start with a stub provider; configure via web UI
        from comobot.providers.base import LLMProvider, LLMResponse

        class _UnconfiguredProvider(LLMProvider):
            def get_default_model(self) -> str:
                return model

            async def chat(
                self,
                messages,
                tools=None,
                model=None,
                max_tokens=4096,
                temperature=0.7,
                reasoning_effort=None,
            ) -> LLMResponse:
                return LLMResponse(
                    content=(
                        "No API key configured. "
                        "Please set your provider API key via the web panel "
                        "(http://localhost:18790) or in ~/.comobot/config.json, "
                        "then restart the gateway."
                    ),
                    finish_reason="stop",
                )

        return _UnconfiguredProvider()

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


# ============================================================================
# Gateway / Server
# ============================================================================

gateway_app = typer.Typer(
    name="gateway",
    help="Manage the comobot gateway.",
    invoke_without_command=True,
)
app.add_typer(gateway_app)


@gateway_app.callback()
def gateway(
    ctx: typer.Context,
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the comobot gateway (or manage it with subcommands)."""
    if ctx.invoked_subcommand is not None:
        return
    _gateway_start(port=port, verbose=verbose)


def _gateway_start(
    port: int = 18790,
    verbose: bool = False,
):
    """Start the comobot gateway."""
    import logging

    from loguru import logger

    from comobot.agent.loop import AgentLoop
    from comobot.bus.queue import MessageBus
    from comobot.channels.manager import ChannelManager
    from comobot.config.loader import get_data_dir, load_config
    from comobot.cron.service import CronService
    from comobot.cron.types import CronJob
    from comobot.heartbeat.service import HeartbeatService
    from comobot.session.manager import SessionManager
    from comobot.utils.log_sanitizer import loguru_sanitize_filter

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "lark_oapi", "lark", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Configure loguru file logging with sanitization
    log_file = _get_log_dir() / "gateway.log"
    logger.add(
        str(log_file),
        rotation="10 MB",
        retention="7 days",
        level="DEBUG" if verbose else "INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        filter=loguru_sanitize_filter,
    )
    logger.enable("comobot")

    # Write PID file and store port for restart API
    _write_pid_file()
    os.environ["COMOBOT_PORT"] = str(port)

    console.print(f"{__logo__} Starting comobot gateway on port {port}...")

    config = load_config()
    sync_workspace_templates(config.workspace_path)

    # Run storage migration checks before anything accesses data
    from comobot.utils.migrate import check_and_migrate

    check_and_migrate(get_data_dir(), config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config, require_key=False)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        memory_config=config.agents.defaults.memory,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        from comobot.agent.tools.cron import CronTool

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )

        # Prevent the agent from scheduling new cron jobs during execution
        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        channel_name = job.payload.channel or "cli"

        # For web channel, always deliver via WebSocket (ChannelManager doesn't handle "web")
        if channel_name == "web" and job.payload.to and response:
            from comobot.api.routes.ws import get_ws_manager

            ws_mgr = get_ws_manager()
            # Notify cron view
            await ws_mgr.broadcast_cron(
                {
                    "type": "job_notification",
                    "job_name": job.name,
                    "message": response,
                    "session_key": job.payload.to,
                }
            )
            # Deliver to the chat view as a response message
            await ws_mgr.broadcast_chat(
                job.payload.to,
                {
                    "type": "response",
                    "session_key": job.payload.to,
                    "content": (f"**[Scheduled Task: {job.name}]**\n\n{response}"),
                    "role": "assistant",
                },
            )
        elif job.payload.deliver and job.payload.to and response:
            from comobot.bus.events import OutboundMessage

            await bus.publish_outbound(
                OutboundMessage(channel=channel_name, chat_id=job.payload.to, content=response)
            )
        return response

    cron.on_job = on_cron_job

    # Wire cron events to WebSocket broadcast (connected after app creation)
    async def on_cron_event(data: dict) -> None:
        from comobot.api.routes.ws import get_ws_manager

        ws_mgr = get_ws_manager()
        await ws_mgr.broadcast_cron(data)

    cron.on_event = on_cron_event

    # Create channel manager
    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        enabled = set(channels.enabled_channels)
        # Prefer the most recently updated non-internal session on an enabled channel.
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        # Fallback keeps prior behavior but remains explicit.
        return "cli", "direct"

    # Create heartbeat service
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver a heartbeat response to the user's channel."""
        from comobot.bus.events import OutboundMessage

        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return  # No external channel available to deliver to
        await bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=response)
        )

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    # Warn if no API key is configured
    _p = config.get_provider(config.agents.defaults.model)
    _model = config.agents.defaults.model
    from comobot.providers.registry import find_by_name as _find_spec

    _spec = _find_spec(config.get_provider_name(_model))
    _no_key = (
        not _model.startswith("bedrock/")
        and not (_p and _p.api_key)
        and not (_spec and _spec.is_oauth)
    )
    if _no_key:
        console.print(
            f"[yellow]Warning: No API key configured. "
            f"Open http://0.0.0.0:{port} to configure via web panel.[/yellow]"
        )

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

    # Memory backend status
    _mem_cfg = config.agents.defaults.memory
    if agent._memory_backend:
        from comobot.agent.memory_backend import FallbackBackend

        if isinstance(agent._memory_backend, FallbackBackend):
            fb = agent._memory_backend
            if fb.primary_active:
                _qmd_mode = _mem_cfg.qmd.mode
                console.print(f"[green]✓[/green] Memory search: QMD active (mode={_qmd_mode})")
            else:
                console.print(
                    "[green]✓[/green] Memory search: builtin (BM25 hybrid)"
                    " [dim]| QMD hot-swap ready[/dim]"
                )
        else:
            console.print("[green]✓[/green] Memory search: builtin (BM25 hybrid)")
    elif agent._memory_engine:
        console.print("[green]✓[/green] Memory search: builtin (BM25 hybrid)")
    else:
        console.print("[yellow]Warning: Memory search disabled[/yellow]")

    if _mem_cfg.session_index.enabled:
        console.print("[green]✓[/green] Session indexing: enabled")

    async def run():
        db = None
        server = None
        shutdown_event = asyncio.Event()

        async def _graceful_shutdown():
            """Stop accepting new work, drain active tasks, then clean up."""
            console.print("\n[yellow]Graceful shutdown initiated...[/yellow]")

            # 1. Stop accepting new messages
            agent.stop()
            console.print("  [dim]Stopped accepting new messages[/dim]")

            # 2. Stop cron and heartbeat (no new jobs)
            heartbeat.stop()
            cron.stop()
            console.print("  [dim]Stopped cron and heartbeat[/dim]")

            # 3. Wait for active session locks to drain (up to 30s)
            deadline = asyncio.get_event_loop().time() + 30
            while agent._session_locks and asyncio.get_event_loop().time() < deadline:
                busy = [k for k, v in agent._session_locks.items() if v.locked()]
                if not busy:
                    break
                console.print(f"  [dim]Waiting for {len(busy)} active session(s)...[/dim]")
                await asyncio.sleep(1)

            # 4. Stop channels
            await channels.stop_all()
            console.print("  [dim]Channels stopped[/dim]")

            # 5. Close MCP connections
            await agent.close_mcp()

            # 6. Stop uvicorn server
            if server is not None:
                server.should_exit = True

            # 7. Close database
            if db is not None:
                try:
                    await db.close()
                except Exception:
                    pass

            _remove_pid_file()
            console.print("[green]Shutdown complete.[/green]")
            shutdown_event.set()

        def _signal_handler():
            asyncio.ensure_future(_graceful_shutdown())

        try:
            # Initialize SQLite database
            from comobot.api.app import create_app
            from comobot.db.connection import Database
            from comobot.db.migrations import run_migrations
            from comobot.security.auth import AuthManager
            from comobot.security.crypto import CredentialVault

            db_path = get_data_dir() / "comobot.db"
            db = Database(db_path)
            await db.connect()
            await run_migrations(db)

            # Wire SQLiteSessionManager for DB sync (external channels → web UI)
            from comobot.session.sqlite_manager import SQLiteSessionManager

            db_session_manager = SQLiteSessionManager(db)
            agent.set_db_session_manager(db_session_manager)

            # Register Know-how tools now that DB is available
            agent.register_knowhow_tools(db)

            vault = CredentialVault(db)
            auth = AuthManager(db)
            await auth.ensure_jwt_secret()

            # Create FastAPI app
            fastapi_app = create_app(
                db=db,
                vault=vault,
                auth=auth,
                agent=agent,
                channels=channels,
                bus=bus,
                cron=cron,
            )

            import uvicorn

            uvi_config = uvicorn.Config(
                fastapi_app,
                host="0.0.0.0",
                port=port,
                log_level="warning",
            )
            server = uvicorn.Server(uvi_config)

            url = f"http://localhost:{port}"
            console.print(f"[green]✓[/green] Web panel: {url}")

            # Register signal handlers for graceful shutdown
            # add_signal_handler is not supported on Windows
            if sys.platform != "win32":
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, _signal_handler)

            async def _open_browser() -> None:
                """Wait for server to be ready, then open browser."""
                import webbrowser

                while not server.started:
                    await asyncio.sleep(0.1)
                webbrowser.open(url)

            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
                server.serve(),
                _open_browser(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            if not shutdown_event.is_set():
                # Fallback cleanup if signal handler didn't run
                await agent.close_mcp()
                heartbeat.stop()
                cron.stop()
                agent.stop()
                await channels.stop_all()
                if db is not None:
                    try:
                        await db.close()
                    except Exception:
                        pass
                _remove_pid_file()

    asyncio.run(run())


@gateway_app.command()
def restart(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Restart the comobot gateway."""
    import time

    console.print("[yellow]Stopping gateway...[/yellow]")
    stopped = _stop_gateway(port)
    if stopped:
        # Wait for the old process to release the port
        for _ in range(30):
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{port}"],
                    capture_output=True,
                    text=True,
                )
                if not result.stdout.strip():
                    break
            except FileNotFoundError:
                break
            time.sleep(0.5)
        console.print("[green]Gateway stopped.[/green]")
    else:
        console.print("[dim]No running gateway found.[/dim]")

    console.print("[yellow]Starting gateway...[/yellow]")

    # Determine the comobot executable path
    comobot_bin = sys.executable.replace("/python", "/comobot")
    if not Path(comobot_bin).exists():
        # Fallback: use sys.argv[0] or search PATH
        comobot_bin = "comobot"

    cmd = [comobot_bin, "gateway", "--port", str(port)]
    if verbose:
        cmd.append("--verbose")

    log_file = _get_log_dir() / "gateway.log"

    # Start gateway as a detached background process (with sanitized output)
    from comobot.utils.log_sanitizer import SanitizedFileWriter

    lf = SanitizedFileWriter(str(log_file))
    proc = subprocess.Popen(
        cmd,
        stdout=lf,
        stderr=lf,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    console.print(f"[green]✓[/green] Gateway started (pid={proc.pid})")
    console.print(f"[green]✓[/green] Logs: {log_file}")
    console.print(f"[green]✓[/green] Web panel: http://localhost:{port}")


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show comobot runtime logs during chat"
    ),
):
    """Interact with the agent directly."""
    from loguru import logger

    from comobot.agent.loop import AgentLoop
    from comobot.bus.queue import MessageBus
    from comobot.config.loader import get_data_dir, load_config
    from comobot.cron.service import CronService

    config = load_config()
    sync_workspace_templates(config.workspace_path)

    # Run storage migration checks
    from comobot.utils.migrate import check_and_migrate

    check_and_migrate(get_data_dir(), config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("comobot")
    else:
        logger.disable("comobot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        memory_config=config.agents.defaults.memory,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext

            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]comobot is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(
                    message, session_id, on_progress=_cli_progress
                )
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from comobot.bus.events import InboundMessage

        _init_prompt_session()
        console.print(
            f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
        )

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(
                            InboundMessage(
                                channel=cli_channel,
                                sender_id="user",
                                chat_id=cli_chat_id,
                                content=user_input,
                            )
                        )

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from comobot.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row("WhatsApp", "✓" if wa.enabled else "✗", wa.bridge_url)

    dc = config.channels.discord
    table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)

    # DingTalk
    dt = config.channels.dingtalk
    dt_config = (
        f"client_id: {dt.client_id[:10]}..." if dt.client_id else "[dim]not configured[/dim]"
    )
    table.add_row("DingTalk", "✓" if dt.enabled else "✗", dt_config)

    # QQ
    qq = config.channels.qq
    qq_config = f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
    table.add_row("QQ", "✓" if qq.enabled else "✗", qq_config)

    # WeChat
    wc = config.channels.wechat
    wc_cred = Path.home() / ".comobot" / "wechat-auth" / "credentials.json"
    wc_status = "logged in" if wc_cred.exists() else "[dim]not logged in[/dim]"
    table.add_row("WeChat", "✓" if wc.enabled else "✗", wc_status)

    # Email
    em = config.channels.email
    em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
    table.add_row("Email", "✓" if em.enabled else "✗", em_config)

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    user_bridge = Path.home() / ".comobot" / "bridge"

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # comobot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall comobot")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


def _try_display_img_content(raw: str) -> bool:
    """Try to decode qrcode_img_content and display QR in terminal. Returns True if successful."""
    import base64

    # Try base64 decode → image → pyzbar decode → terminal QR
    for decode_fn in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            img_data = decode_fn(raw)
            if len(img_data) < 100:
                continue  # Too small to be an image
            # Check for known image headers
            if img_data[:4] not in (b"\x89PNG", b"\xff\xd8\xff", b"GIF8"):
                continue
            from PIL import Image
            from pyzbar.pyzbar import decode as decode_qr

            img = Image.open(io.BytesIO(img_data))
            results = decode_qr(img)
            if results:
                qr_url = results[0].data.decode()
                console.print(f"[dim]QR content: {qr_url}[/dim]\n")
                import qrcode as qr_lib

                qr = qr_lib.QRCode(border=1)
                qr.add_data(qr_url)
                qr.make(fit=True)
                qr.print_ascii(invert=True)
                return True
        except Exception:
            continue

    # qrcode_img_content might itself be a URL or scannable string
    if raw.startswith(("http://", "https://")):
        try:
            import qrcode as qr_lib

            console.print(f"[dim]QR URL: {raw}[/dim]\n")
            qr = qr_lib.QRCode(border=1)
            qr.add_data(raw)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            return True
        except Exception:
            pass

    return False


def _wechat_login() -> None:
    """WeChat login via iLink QR code scan."""
    import base64
    import json
    import random
    import time

    import httpx

    from comobot.config.loader import load_config

    config = load_config()
    base_url = config.channels.wechat.base_url.rstrip("/")
    uin = base64.b64encode(str(random.randint(0, 2**32 - 1)).encode()).decode()

    console.print(f"{__logo__} WeChat Login via iLink API\n")

    # Step 1: Get QR code
    console.print("Fetching QR code...")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{base_url}/ilink/bot/get_bot_qrcode",
                params={"bot_type": "3"},
                headers={"X-WECHAT-UIN": uin},
            )
            data = resp.json()
    except Exception as e:
        console.print(f"[red]Failed to fetch QR code: {e}[/red]")
        return

    qrcode_token = data.get("qrcode", "")
    qrcode_img_raw = data.get("qrcode_img_content", "")

    if not qrcode_token:
        console.print(f"[red]No QR code in response: {data}[/red]")
        return

    # Debug: inspect qrcode_img_content to understand its format
    if qrcode_img_raw:
        console.print(
            f"[dim]qrcode_img_content: type={type(qrcode_img_raw).__name__}, "
            f"len={len(qrcode_img_raw)}, preview={str(qrcode_img_raw)[:120]}[/dim]"
        )

    # Try to extract a scannable URL/image from qrcode_img_content
    qr_displayed = False
    if qrcode_img_raw:
        qr_displayed = _try_display_img_content(qrcode_img_raw)

    # Fallback: generate terminal QR from the token directly.
    # WeChat's scanner may recognize the raw token as an iLink login code.
    if not qr_displayed:
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(border=1)
            qr.add_data(qrcode_token)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            console.print(f"\n[dim]QR content: {qrcode_token}[/dim]")
        except ImportError:
            console.print(f"QR token: [bold]{qrcode_token}[/bold]")
            console.print("[dim]pip install qrcode for terminal QR display[/dim]")

    console.print("\nWaiting for scan...")

    # Step 2: Poll for QR code status
    qrcode_param = qrcode_token
    try:
        with httpx.Client(timeout=45) as client:
            for _ in range(30):  # ~20 min max
                try:
                    resp = client.get(
                        f"{base_url}/ilink/bot/get_qrcode_status",
                        params={"qrcode": qrcode_param},
                        headers={"X-WECHAT-UIN": uin},
                        timeout=45,
                    )
                    status_data = resp.json()
                except httpx.ReadTimeout:
                    continue

                status = status_data.get("status", "")
                if status == "confirmed":
                    bot_token = status_data.get("bot_token", "")
                    bot_id = status_data.get("bot_id", "")
                    user_id = status_data.get("user_id", "")

                    if not bot_token:
                        console.print("[red]Login confirmed but no bot_token received.[/red]")
                        return

                    # Save credentials
                    auth_dir = Path.home() / ".comobot" / "wechat-auth"
                    auth_dir.mkdir(parents=True, exist_ok=True)
                    creds = {
                        "token": bot_token,
                        "base_url": base_url,
                        "bot_id": bot_id,
                        "user_id": user_id,
                        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    (auth_dir / "credentials.json").write_text(
                        json.dumps(creds, indent=2, ensure_ascii=False)
                    )

                    console.print("\n[green]✓ WeChat login successful![/green]")
                    console.print(f"  Bot ID: {bot_id}")
                    console.print(f"  Credentials saved to: {auth_dir / 'credentials.json'}")

                    # Auto-enable WeChat in config
                    from comobot.config.loader import load_config, save_config

                    config = load_config()
                    if not config.channels.wechat.enabled:
                        config.channels.wechat.enabled = True
                        if not config.channels.wechat.allow_from:
                            config.channels.wechat.allow_from = ["*"]
                        save_config(config)
                        console.print("[green]✓ WeChat enabled in config.[/green]")
                    else:
                        console.print("[dim]WeChat already enabled in config.[/dim]")

                    # Restart gateway if running
                    port = config.gateway.port if hasattr(config.gateway, "port") else 18790
                    try:
                        result = subprocess.run(
                            ["lsof", "-ti", f"tcp:{port}"],
                            capture_output=True,
                            text=True,
                        )
                        if result.stdout.strip():
                            console.print("[yellow]Restarting gateway...[/yellow]")
                            restart(port=port)
                        else:
                            console.print(
                                "[dim]Gateway not running. Start with: comobot gateway[/dim]"
                            )
                    except FileNotFoundError:
                        console.print("[dim]Gateway not running. Start with: comobot gateway[/dim]")
                    return

                if status == "expired":
                    console.print("[red]QR code expired. Please try again.[/red]")
                    return

                if status == "scanned":
                    console.print("Scanned! Waiting for confirmation...")

                time.sleep(1)

        console.print("[red]Timed out waiting for scan.[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Login cancelled.[/yellow]")


@channels_app.command("login")
def channels_login(
    channel: str = typer.Argument("whatsapp", help="Channel to login (whatsapp, wechat)"),
):
    """Link device via QR code."""
    if channel == "wechat":
        _wechat_login()
        return

    import subprocess

    from comobot.config.loader import load_config

    config = load_config()
    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show comobot status."""
    from comobot.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} comobot Status\n")

    console.print(
        f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
    )
    console.print(
        f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
    )

    if config_path.exists():
        from comobot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(
                    f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"
                )


# ============================================================================
# Uninstall
# ============================================================================


@app.command()
def uninstall(
    all_data: bool = typer.Option(
        False, "--all", help="Remove all data including config, database, and workspace"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
):
    """Uninstall comobot from this machine."""
    import shutil
    import subprocess

    home = Path.home()
    data_dir = home / ".comobot"
    bin_dir = data_dir / "bin"
    binary = bin_dir / "comobot"
    symlink = Path("/usr/local/bin/comobot")
    shell_rcs = [home / ".zshrc", home / ".bashrc", home / ".profile"]

    # ── Summary ──────────────────────────────────────────────────────────
    console.print(f"{__logo__} comobot Uninstaller\n")
    console.print("[bold]The following will be removed:[/bold]")
    if binary.exists():
        console.print(f"  • Binary:  {binary}")
    if symlink.is_symlink() or symlink.exists():
        console.print(f"  • Symlink: {symlink}")
    for rc in shell_rcs:
        if rc.exists() and ".comobot/bin" in rc.read_text(errors="ignore"):
            console.print(f"  • PATH entry in {rc}")
    if all_data:
        console.print(f"  • [red]All data:  {data_dir}[/red]  (config, database, workspace, logs)")
    else:
        console.print(f"  • Binary dir: {bin_dir}")
        console.print("  [dim]Tip: use --all to also remove config, database, and workspace[/dim]")
    console.print()

    # ── Gateway stop ─────────────────────────────────────────────────────
    console.print("[bold]Running gateway process will be stopped.[/bold]")
    console.print()

    # ── Confirm ──────────────────────────────────────────────────────────
    if not yes:
        confirm = typer.confirm("Proceed with uninstall?", default=False)
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    # ── Stop gateway ─────────────────────────────────────────────────────
    console.print("Stopping gateway process...")
    # Kill any running comobot gateway processes (but not ourselves)
    my_pid = str(os.getpid())
    try:
        result = subprocess.run(
            ["pgrep", "-f", "comobot gateway"],
            capture_output=True,
            text=True,
        )
        for pid in result.stdout.strip().splitlines():
            pid = pid.strip()
            if pid and pid != my_pid:
                subprocess.run(["kill", pid], capture_output=True)
                console.print(f"  Stopped process {pid}")
    except FileNotFoundError:
        pass  # pgrep not available on this platform

    # Also try killing by port (default 18790)
    try:
        result = subprocess.run(
            ["lsof", "-ti", "tcp:18790"],
            capture_output=True,
            text=True,
        )
        for pid in result.stdout.strip().splitlines():
            pid = pid.strip()
            if pid and pid != my_pid:
                subprocess.run(["kill", pid], capture_output=True)
    except FileNotFoundError:
        pass

    # ── Remove symlink ───────────────────────────────────────────────────
    if symlink.is_symlink() or symlink.exists():
        try:
            symlink.unlink()
            console.print(f"  [green]✓[/green] Removed {symlink}")
        except PermissionError:
            try:
                subprocess.run(["sudo", "rm", "-f", str(symlink)], check=True)
                console.print(f"  [green]✓[/green] Removed {symlink} (sudo)")
            except Exception:
                console.print(
                    f"  [yellow]⚠[/yellow] Could not remove {symlink}, please delete manually"
                )

    # ── Clean shell rc PATH entries ──────────────────────────────────────
    for rc in shell_rcs:
        if not rc.exists():
            continue
        original = rc.read_text(errors="ignore")
        lines = original.splitlines(keepends=True)
        cleaned: list[str] = []
        skip_next_blank = False
        for line in lines:
            stripped = line.strip()
            # Remove the comobot PATH line and its "# Comobot" comment
            if ".comobot/bin" in stripped or stripped == "# Comobot":
                skip_next_blank = True
                continue
            if skip_next_blank and stripped == "":
                skip_next_blank = False
                continue
            skip_next_blank = False
            cleaned.append(line)
        new_text = "".join(cleaned)
        if new_text != original:
            rc.write_text(new_text)
            console.print(f"  [green]✓[/green] Cleaned PATH from {rc}")

    # ── Remove files ─────────────────────────────────────────────────────
    if all_data:
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            console.print(f"  [green]✓[/green] Removed {data_dir}")
    else:
        # Only remove the bin directory
        if binary.exists():
            binary.unlink()
            console.print(f"  [green]✓[/green] Removed {binary}")
        if bin_dir.exists() and not any(bin_dir.iterdir()):
            bin_dir.rmdir()

    console.print()
    console.print("[bold green]comobot has been uninstalled.[/bold green]")
    if not all_data and data_dir.exists():
        console.print(f"[dim]Your data is preserved in {data_dir}. Use --all to remove it.[/dim]")


# ============================================================================
# Update
# ============================================================================


def _detect_install_method() -> str:
    """Detect how comobot was installed.

    Returns one of: 'binary', 'pip', 'docker'.
    """
    # Docker: check /.dockerenv or /proc/1/cgroup
    if Path("/.dockerenv").exists():
        return "docker"
    try:
        cgroup = Path("/proc/1/cgroup").read_text(errors="ignore")
        if "docker" in cgroup or "containerd" in cgroup:
            return "docker"
    except OSError:
        pass

    # PyInstaller binary: sys._MEIPASS is set
    if getattr(sys, "_MEIPASS", None):
        return "binary"

    # Binary install via install.sh: ~/.comobot/bin/comobot exists
    binary_path = Path.home() / ".comobot" / "bin" / "comobot"
    if binary_path.exists():
        return "binary"

    # Default: assume pip
    return "pip"


def _ssl_context():
    """Create an SSL context that works in PyInstaller frozen binaries."""
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def _fetch_latest_version() -> str | None:
    """Fetch the latest release version from GitHub."""
    import json as _json
    import urllib.request

    repo = "musenming/comobot"
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as resp:
            data = _json.loads(resp.read())
        return data.get("tag_name", "").lstrip("v")
    except Exception as exc:
        console.print(f"  [dim]Debug: {type(exc).__name__}: {exc}[/dim]")
        return None


def _update_binary(version: str) -> None:
    """Update binary installation by downloading the latest release."""
    import platform
    import tarfile
    import tempfile
    import urllib.request
    import zipfile

    repo = "musenming/comobot"
    install_dir = Path.home() / ".comobot" / "bin"

    # Detect platform
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        plat = "macos"
    elif system == "linux":
        plat = "linux"
    elif system == "windows":
        plat = "windows"
    else:
        console.print(f"[red]Unsupported OS: {system}[/red]")
        raise typer.Exit(1)

    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        console.print(f"[red]Unsupported architecture: {machine}[/red]")
        raise typer.Exit(1)

    target = f"{plat}-{arch}"
    console.print(f"  Platform: [cyan]{target}[/cyan]")

    if plat == "windows":
        asset_name = f"comobot-{version}-{target}.zip"
    else:
        asset_name = f"comobot-{version}-{target}.tar.gz"
    download_url = f"https://github.com/{repo}/releases/download/v{version}/{asset_name}"

    # Download
    console.print(f"  Downloading [cyan]{asset_name}[/cyan]...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / asset_name

        try:
            req = urllib.request.Request(download_url)
            with urllib.request.urlopen(req, context=_ssl_context()) as resp:
                archive_path.write_bytes(resp.read())
        except Exception as exc:
            console.print(f"[red]Download failed: {exc}[/red]")
            raise typer.Exit(1)

        # Extract
        console.print("  Extracting...")
        if asset_name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_path)
            new_binary = tmp_path / "comobot" / "comobot"
        else:
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(tmp_path)
            new_binary = tmp_path / "comobot" / "comobot.exe"

        if not new_binary.exists():
            console.print("[red]Unexpected archive structure.[/red]")
            raise typer.Exit(1)

        # Install
        install_dir.mkdir(parents=True, exist_ok=True)
        dest = install_dir / new_binary.name
        import shutil

        shutil.copy2(new_binary, dest)
        if plat != "windows":
            dest.chmod(0o755)

    console.print(f"  [green]✓[/green] Updated binary at {dest}")


def _update_pip() -> None:
    """Update pip installation."""
    console.print("  Running [cyan]pip install --upgrade comobot[/cyan]...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "comobot"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]pip upgrade failed:[/red]\n{result.stderr}")
        raise typer.Exit(1)
    console.print("  [green]✓[/green] pip upgrade complete")


def _update_docker() -> None:
    """Update Docker installation."""
    image = "ghcr.io/musenming/comobot:latest"
    console.print(f"  Pulling [cyan]{image}[/cyan]...")
    result = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]docker pull failed:[/red]\n{result.stderr}")
        raise typer.Exit(1)
    console.print("  [green]✓[/green] Pulled latest image")
    console.print(
        "\n  [yellow]Note:[/yellow] Please restart your container to use the new version."
    )
    console.print("  e.g. [cyan]docker compose up -d[/cyan] or [cyan]docker restart comobot[/cyan]")


@app.command()
def update(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Update comobot to the latest version."""
    console.print(f"{__logo__} comobot Updater\n")
    console.print(f"  Current:  [cyan]v{__version__}[/cyan]")

    # Detect installation method
    method = _detect_install_method()
    console.print(f"  Install:  [cyan]{method}[/cyan]")

    # Check latest version
    latest = _fetch_latest_version()
    if not latest:
        console.print(
            "  Latest:   [red]unknown (could not reach GitHub)[/red]\n"
            "\n[red]Cannot update without knowing the latest version.[/red]"
        )
        raise typer.Exit(1)

    console.print(f"  Latest:   [cyan]v{latest}[/cyan]")
    if latest == __version__:
        console.print("\n[green]You are already on the latest version.[/green]")
        return

    console.print()

    # Confirm
    if not yes:
        confirm = typer.confirm(f"Update comobot via {method}?", default=True)
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    console.print()

    if method == "binary":
        _update_binary(latest)
    elif method == "pip":
        _update_pip()
    elif method == "docker":
        _update_docker()

    console.print("\n[bold green]comobot has been updated![/bold green]")


# ============================================================================
# Download stats
# ============================================================================


@app.command()
def stats():
    """Show GitHub release download statistics."""
    import json as _json
    import urllib.request

    repo = "musenming/comobot"
    url = f"https://api.github.com/repos/{repo}/releases"

    console.print(f"{__logo__} comobot Download Statistics\n")

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            releases = _json.loads(resp.read())
    except Exception as exc:
        console.print(f"[red]Failed to fetch release data: {exc}[/red]")
        raise typer.Exit(1)

    if not releases:
        console.print("[dim]No releases found.[/dim]")
        return

    total_downloads = 0

    for rel in releases:
        tag = rel["tag_name"]
        published = (rel.get("published_at") or "")[:10]
        assets = rel.get("assets", [])
        rel_total = sum(a["download_count"] for a in assets)
        total_downloads += rel_total

        table = Table(
            title=f"{tag}  ({published})  Total: {rel_total}",
            title_style="bold cyan",
            show_header=True,
            header_style="bold",
            padding=(0, 1),
        )
        table.add_column("Asset", style="white", no_wrap=True)
        table.add_column("Downloads", justify="right", style="green")

        for asset in assets:
            name = asset["name"]
            count = asset["download_count"]
            table.add_row(name, str(count))

        if not assets:
            table.add_row("[dim]no assets[/dim]", "-")

        console.print(table)
        console.print()

    console.print(
        f"[bold]Total downloads across all releases: [green]{total_downloads}[/green][/bold]"
    )


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn

    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(
        ..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"
    ),
):
    """Authenticate with an OAuth provider."""
    from comobot.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive

        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(
            f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]"
        )
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion

        await acompletion(
            model="github_copilot/gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
