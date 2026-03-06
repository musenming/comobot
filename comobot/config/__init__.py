"""Configuration module for comobot."""

from comobot.config.loader import get_config_path, load_config
from comobot.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
