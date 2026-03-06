"""Message bus module for decoupled channel-agent communication."""

from comobot.bus.events import InboundMessage, OutboundMessage
from comobot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
