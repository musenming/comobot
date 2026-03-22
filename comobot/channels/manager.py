"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from comobot.bus.queue import MessageBus
from comobot.channels.base import BaseChannel
from comobot.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels dynamically
    - Route outbound messages
    """

    # Channel factory: name -> (module_path, class_name)
    CHANNEL_REGISTRY: dict[str, tuple[str, str]] = {
        "telegram": ("comobot.channels.telegram", "TelegramChannel"),
        "whatsapp": ("comobot.channels.whatsapp", "WhatsAppChannel"),
        "discord": ("comobot.channels.discord", "DiscordChannel"),
        "feishu": ("comobot.channels.feishu", "FeishuChannel"),
        "mochat": ("comobot.channels.mochat", "MochatChannel"),
        "dingtalk": ("comobot.channels.dingtalk", "DingTalkChannel"),
        "email": ("comobot.channels.email", "EmailChannel"),
        "slack": ("comobot.channels.slack", "SlackChannel"),
        "qq": ("comobot.channels.qq", "QQChannel"),
        "wechat": ("comobot.channels.wechat", "WechatChannel"),
        "matrix": ("comobot.channels.matrix", "MatrixChannel"),
    }

    def __init__(self, config: Config, bus: MessageBus):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._channel_tasks: dict[str, asyncio.Task] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _create_channel(self, name: str) -> BaseChannel | None:
        """Create a channel instance by name using the registry."""
        import importlib

        entry = self.CHANNEL_REGISTRY.get(name)
        if not entry:
            logger.warning("Unknown channel: {}", name)
            return None

        module_path, class_name = entry
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
        except ImportError as e:
            logger.warning("{} channel not available: {}", name, e)
            return None

        ch_cfg = getattr(self.config.channels, name, None)
        if ch_cfg is None:
            return None

        # Telegram needs extra kwargs
        if name == "telegram":
            return cls(ch_cfg, self.bus, groq_api_key=self.config.providers.groq.api_key)
        return cls(ch_cfg, self.bus)

    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        for name in self.CHANNEL_REGISTRY:
            ch_cfg = getattr(self.config.channels, name, None)
            if ch_cfg is not None and ch_cfg.enabled:
                channel = self._create_channel(name)
                if channel:
                    self.channels[name] = channel
                    logger.info("{} channel enabled", name)

        self._validate_allow_from()

    def _validate_allow_from(self) -> None:
        for name, ch in self.channels.items():
            if getattr(ch.config, "allow_from", None) == []:
                raise SystemExit(
                    f'Error: "{name}" has empty allowFrom (denies all). '
                    f'Set ["*"] to allow everyone, or add specific user IDs.'
                )

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("Failed to start channel {}: {}", name, e)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("Starting {} channel...", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("Stopped {} channel", name)
            except Exception as e:
                logger.error("Error stopping {}: {}", name, e)

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        while True:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)

                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not self.config.channels.send_tool_hints:
                        continue
                    if (
                        not msg.metadata.get("_tool_hint")
                        and not self.config.channels.send_progress
                    ):
                        continue

                channel = self.channels.get(msg.channel)
                logger.debug("Dispatching to channel={}, chat_id={}", msg.channel, msg.chat_id)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error("Error sending to {}: {}", msg.channel, e)
                else:
                    logger.warning("Unknown channel: {}", msg.channel)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def start_channel(self, name: str) -> bool:
        """Dynamically start a single channel at runtime."""
        if name in self.channels:
            logger.info("Channel {} already running, restarting...", name)
            await self.stop_channel(name)

        channel = self._create_channel(name)
        if not channel:
            return False

        self.channels[name] = channel
        self._validate_allow_from()
        logger.info("Starting {} channel...", name)
        task = asyncio.create_task(self._start_channel(name, channel))
        self._channel_tasks[name] = task
        return True

    async def stop_channel(self, name: str) -> bool:
        """Stop and remove a running channel."""
        channel = self.channels.pop(name, None)
        if not channel:
            return False

        try:
            await channel.stop()
            logger.info("Stopped {} channel", name)
        except Exception as e:
            logger.error("Error stopping {}: {}", name, e)

        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return True

    async def reload_channels(self, config: Config) -> dict[str, list[str]]:
        """Reload channels based on updated config. Returns started/stopped channel names."""
        self.config = config
        started: list[str] = []
        stopped: list[str] = []

        for name in self.CHANNEL_REGISTRY:
            ch_cfg = getattr(config.channels, name, None)
            is_enabled = ch_cfg is not None and ch_cfg.enabled
            is_running = name in self.channels

            if is_enabled and not is_running:
                if await self.start_channel(name):
                    started.append(name)
            elif not is_enabled and is_running:
                if await self.stop_channel(name):
                    stopped.append(name)

        return {"started": started, "stopped": stopped}

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {"enabled": True, "running": channel.is_running}
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
