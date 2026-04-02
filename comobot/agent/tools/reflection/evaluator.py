"""Rule-based tool result evaluator with pluggable checkers."""

from __future__ import annotations

import re
from typing import Protocol

from comobot.agent.tools.reflection.models import Action, EvalResult, Issue, Quality


class ToolChecker(Protocol):
    """Protocol for tool-specific quality checkers."""

    def applies_to(self, tool_name: str) -> bool: ...
    def check(
        self, tool_name: str, params: dict, result: str, elapsed_ms: float
    ) -> list[Issue]: ...


# ---------------------------------------------------------------------------
# Built-in checkers
# ---------------------------------------------------------------------------


class ErrorPrefixChecker:
    """Detect results that start with 'Error' — the existing convention."""

    def applies_to(self, tool_name: str) -> bool:
        return True

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        if result.startswith("Error"):
            return [Issue(code="error_prefix", message=result[:200], retryable=True)]
        return []


class SearchQualityChecker:
    """Detect low-quality web search results."""

    _NO_RESULT_PATTERNS = (
        re.compile(r"no\s+results?\s+found", re.I),
        re.compile(r"没有找到", re.I),
        re.compile(r"未找到相关", re.I),
        re.compile(r"\[\s*\]"),  # empty JSON array
    )

    def applies_to(self, tool_name: str) -> bool:
        return tool_name == "web_search"

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        for pat in self._NO_RESULT_PATTERNS:
            if pat.search(result):
                query = params.get("query", "")
                return [
                    Issue(
                        code="search_no_results",
                        message=f"Search returned no results for: {query[:80]}",
                        retryable=True,
                        retry_hint="broaden_query",
                    )
                ]
        return []


class FileNotFoundChecker:
    """Detect file-not-found errors in filesystem tools."""

    _PATTERNS = (
        re.compile(r"no such file|not found|does not exist|FileNotFoundError", re.I),
        re.compile(r"文件不存在|找不到文件|路径不存在", re.I),
    )

    def applies_to(self, tool_name: str) -> bool:
        return tool_name in ("read_file", "edit_file")

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        for pat in self._PATTERNS:
            if pat.search(result):
                path = params.get("path", params.get("file_path", ""))
                return [
                    Issue(
                        code="file_not_found",
                        message=f"File not found: {path}",
                        retryable=True,
                        retry_hint="fuzzy_path",
                    )
                ]
        return []


class ExecErrorChecker:
    """Detect shell command failures."""

    _ERROR_PATTERNS = (
        re.compile(r"command not found", re.I),
        re.compile(r"permission denied", re.I),
        re.compile(r"exit code[:\s]+[1-9]", re.I),
        re.compile(r"Traceback \(most recent call last\)", re.I),
    )

    def applies_to(self, tool_name: str) -> bool:
        return tool_name == "exec"

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        issues: list[Issue] = []
        for pat in self._ERROR_PATTERNS:
            if pat.search(result):
                issues.append(
                    Issue(
                        code="exec_error",
                        message=f"Command error detected: {pat.pattern[:60]}",
                        retryable="permission denied" not in result.lower(),
                    )
                )
                break
        return issues


class WebFetchChecker:
    """Detect web fetch failures (HTTP errors, anti-bot, empty pages)."""

    _FAIL_PATTERNS = (
        re.compile(r"HTTP\s+(?:4\d{2}|5\d{2})", re.I),
        re.compile(r"403\s+Forbidden|Access Denied|Cloudflare", re.I),
        re.compile(r"rate.?limit|too many requests", re.I),
        re.compile(r"timed?\s*out|timeout", re.I),
    )

    def applies_to(self, tool_name: str) -> bool:
        return tool_name == "web_fetch"

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        for pat in self._FAIL_PATTERNS:
            if pat.search(result):
                return [
                    Issue(
                        code="web_fetch_error",
                        message=f"Web fetch failed: {pat.pattern[:60]}",
                        retryable=True,
                        retry_hint="retry_with_backoff",
                    )
                ]
        return []


class TruncationChecker:
    """Detect results that appear truncated."""

    _TRUNCATION_SIGNALS = (
        re.compile(r"\.\.\.\s*$"),
        re.compile(r"\[truncated\]", re.I),
        re.compile(r"\[output too long\]", re.I),
        re.compile(r"内容过长.*截断", re.I),
    )

    def applies_to(self, tool_name: str) -> bool:
        return True

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        for pat in self._TRUNCATION_SIGNALS:
            if pat.search(result[-200:] if len(result) > 200 else result):
                return [
                    Issue(
                        code="truncated",
                        message="Result appears truncated",
                        retryable=False,
                    )
                ]
        return []


class EmptyResultChecker:
    """Detect empty or whitespace-only results."""

    _SKIP_TOOLS = frozenset({"write_file", "edit_file", "message"})

    def applies_to(self, tool_name: str) -> bool:
        return tool_name not in self._SKIP_TOOLS

    def check(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> list[Issue]:
        if not result or not result.strip():
            return [
                Issue(
                    code="empty_result",
                    message=f"Tool '{tool_name}' returned empty result",
                    retryable=tool_name in ("web_search", "web_fetch", "exec"),
                    retry_hint="broaden_query" if tool_name == "web_search" else None,
                )
            ]
        return []


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

_DEFAULT_CHECKERS: list[ToolChecker] = [
    ErrorPrefixChecker(),
    EmptyResultChecker(),
    SearchQualityChecker(),
    FileNotFoundChecker(),
    ExecErrorChecker(),
    WebFetchChecker(),
    TruncationChecker(),
]


class ToolResultEvaluator:
    """Rule-based tool result quality evaluator. Zero LLM cost."""

    def __init__(self, checkers: list[ToolChecker] | None = None):
        self._checkers = checkers or list(_DEFAULT_CHECKERS)

    def evaluate(self, tool_name: str, params: dict, result: str, elapsed_ms: float) -> EvalResult:
        all_issues: list[Issue] = []
        for checker in self._checkers:
            if checker.applies_to(tool_name):
                all_issues.extend(checker.check(tool_name, params, result, elapsed_ms))

        if not all_issues:
            return EvalResult(quality=Quality.HIGH, suggested_action=Action.PASS)

        has_retryable = any(i.retryable for i in all_issues)
        has_error = any(i.code in ("error_prefix", "exec_error") for i in all_issues)

        if has_error:
            quality = Quality.FAILED
        elif has_retryable:
            quality = Quality.LOW
        else:
            quality = Quality.MEDIUM

        if has_retryable:
            action = Action.RETRY
        elif quality <= Quality.MEDIUM:
            action = Action.ANNOTATE
        else:
            action = Action.PASS

        return EvalResult(quality=quality, issues=all_issues, suggested_action=action)
