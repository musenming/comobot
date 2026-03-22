"""Log sanitizer to prevent sensitive data from leaking into log files."""

import io
import re

# Patterns that match sensitive values and replace them with redacted versions.
# Each tuple: (compiled regex, replacement string)
_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Authorization headers: Bearer xxx, Basic xxx
    (
        re.compile(r"(Authorization['\"]?\s*[:=]\s*['\"]?)(Bearer|Basic)\s+[^\s'\"}\]]+", re.I),
        r"\1\2 [REDACTED]",
    ),
    # Generic token/key/secret/password values in key=value or "key": "value"
    (
        re.compile(
            r"((?:token|api[_-]?key|secret|password|access[_-]?key|bot[_-]?token|auth[_-]?token)"
            r"['\"]?\s*[:=]\s*['\"]?)([^\s'\"}\],]{8,})",
            re.I,
        ),
        r"\1[REDACTED]",
    ),
    # context_token in WeChat messages (single or double quotes)
    (re.compile(r"(['\"]context_token['\"]\s*:\s*['\"])[^'\"]+(['\"])"), r"\1[REDACTED]\2"),
    # JWT tokens (three base64 segments separated by dots)
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[JWT_REDACTED]"),
    # Feishu/Lark access_key in URLs
    (re.compile(r"(access_key=)[^\s&]+"), r"\1[REDACTED]"),
    # Feishu/Lark ticket in URLs
    (re.compile(r"(ticket=)[^\s&\]]+"), r"\1[REDACTED]"),
]


def sanitize(text: str) -> str:
    """Remove sensitive tokens, keys, and credentials from log text."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def loguru_sanitize_filter(record: dict) -> bool:
    """Loguru filter that sanitizes the message in-place before formatting."""
    msg = record.get("message", "")
    if msg:
        record["message"] = sanitize(msg)
    return True


class SanitizedFileWriter(io.TextIOBase):
    """A file-like writer that sanitizes each line before writing.

    Used as stdout/stderr redirect for subprocess to filter sensitive data
    from third-party libraries (e.g. Feishu/Lark SDK) that log to stdout.
    """

    def __init__(self, path: str, mode: str = "a"):
        self._file = open(path, mode, encoding="utf-8")  # noqa: SIM115

    def write(self, text: str) -> int:
        sanitized = sanitize(text)
        return self._file.write(sanitized)

    def flush(self):
        self._file.flush()

    def fileno(self) -> int:
        return self._file.fileno()

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
