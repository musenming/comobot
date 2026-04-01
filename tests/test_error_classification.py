"""Tests for LLM error classification and retry logic."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def provider():
    from comobot.providers.litellm_provider import LiteLLMProvider

    return LiteLLMProvider(api_key="test-key", default_model="gpt-4o")


class TestClassifyError:
    """Test _classify_error for different litellm exception types."""

    def test_content_policy_violation(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.ContentPolicyViolationError(
            message="Content policy violated",
            model="test",
            llm_provider="openai",
        )
        assert _classify_error(exc) == "content_safety"

    def test_unprocessable_entity_with_sensitive(self):
        import httpx
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        mock_response = httpx.Response(422, request=httpx.Request("POST", "https://test"))
        exc = litellm.UnprocessableEntityError(
            message='MinimaxException - {"error":{"message":"output new_sensitive (1027)"}}',
            model="minimax/MiniMax-M2.1",
            llm_provider="minimax",
            response=mock_response,
        )
        assert _classify_error(exc) == "content_safety"

    def test_unprocessable_entity_without_sensitive(self):
        import httpx
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        mock_response = httpx.Response(422, request=httpx.Request("POST", "https://test"))
        exc = litellm.UnprocessableEntityError(
            message="Some other unprocessable error",
            model="test",
            llm_provider="test",
            response=mock_response,
        )
        assert _classify_error(exc) is None

    def test_api_connection_error_minimax_sensitive(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.APIConnectionError(
            message='MinimaxException - {"error":{"message":"output new_sensitive (1027)"}}',
            model="minimax/MiniMax-M2.1",
            llm_provider="minimax",
        )
        assert _classify_error(exc) == "content_safety"

    def test_api_connection_error_network(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.APIConnectionError(
            message="Connection refused",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "network"

    def test_rate_limit_error(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "rate_limit"

    def test_auth_error(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.AuthenticationError(
            message="Invalid API key",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "auth"

    def test_context_window_exceeded(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.ContextWindowExceededError(
            message="Context length exceeded",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "context_length"

    def test_timeout(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.Timeout(
            message="Request timed out",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "network"

    def test_service_unavailable(self):
        import litellm

        from comobot.providers.litellm_provider import _classify_error

        exc = litellm.ServiceUnavailableError(
            message="Service unavailable",
            model="test",
            llm_provider="test",
        )
        assert _classify_error(exc) == "network"

    def test_generic_exception(self):
        from comobot.providers.litellm_provider import _classify_error

        assert _classify_error(ValueError("something")) is None


class TestRetryLogic:
    """Test retry behavior in LiteLLMProvider.chat()."""

    @pytest.mark.asyncio
    async def test_content_safety_not_retried(self, provider):
        import litellm

        exc = litellm.ContentPolicyViolationError(
            message="Content policy violated",
            model="gpt-4o",
            llm_provider="openai",
        )
        with patch(
            "comobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=exc,
        ) as mock_call:
            result = await provider.chat(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )
            assert result.finish_reason == "error"
            assert result.error_type == "content_safety"
            assert mock_call.await_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_auth_error_not_retried(self, provider):
        import litellm

        exc = litellm.AuthenticationError(
            message="Invalid key",
            model="gpt-4o",
            llm_provider="openai",
        )
        with patch(
            "comobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=exc,
        ) as mock_call:
            result = await provider.chat(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )
            assert result.finish_reason == "error"
            assert result.error_type == "auth"
            assert mock_call.await_count == 1

    @pytest.mark.asyncio
    async def test_network_error_retried(self, provider):
        import litellm


        exc = litellm.APIConnectionError(
            message="Connection refused",
            model="gpt-4o",
            llm_provider="openai",
        )

        # Fake successful response for the retry
        class FakeMsg:
            content = "ok"
            role = "assistant"
            reasoning_content = None
            thinking_blocks = None
            tool_calls = None

        class FakeChoice:
            index = 0
            finish_reason = "stop"
            message = FakeMsg()

        class FakeUsage:
            prompt_tokens = 10
            completion_tokens = 5
            total_tokens = 15

        class FakeResp:
            choices = [FakeChoice()]
            usage = FakeUsage()

        with patch(
            "comobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=[exc, FakeResp()],
        ) as mock_call, patch("comobot.providers.litellm_provider.asyncio.sleep", new_callable=AsyncMock):
            result = await provider.chat(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )
            assert result.finish_reason == "stop"
            assert result.content == "ok"
            assert mock_call.await_count == 2  # 1 failure + 1 retry success

    @pytest.mark.asyncio
    async def test_network_error_exhausts_retries(self, provider):
        import litellm

        exc = litellm.APIConnectionError(
            message="Connection refused",
            model="gpt-4o",
            llm_provider="openai",
        )
        with patch(
            "comobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=exc,
        ) as mock_call, patch("comobot.providers.litellm_provider.asyncio.sleep", new_callable=AsyncMock):
            result = await provider.chat(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )
            assert result.finish_reason == "error"
            assert result.error_type == "network"
            assert mock_call.await_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_rate_limit_retried(self, provider):
        import litellm

        exc = litellm.RateLimitError(
            message="Rate limit",
            model="gpt-4o",
            llm_provider="openai",
        )
        with patch(
            "comobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=exc,
        ) as mock_call, patch("comobot.providers.litellm_provider.asyncio.sleep", new_callable=AsyncMock):
            result = await provider.chat(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )
            assert result.finish_reason == "error"
            assert result.error_type == "rate_limit"
            assert mock_call.await_count == 3  # 1 initial + 2 retries


class TestPerProviderKeyFiltering:
    """Test excluded_msg_keys filtering in _strip_non_standard_keys."""

    def test_excluded_keys_removed(self):
        from comobot.providers.litellm_provider import _strip_non_standard_keys

        messages = [
            {"role": "tool", "tool_call_id": "tc1", "name": "read_file", "content": "data"},
        ]
        result = _strip_non_standard_keys(
            messages, excluded_keys=frozenset({"name"})
        )
        assert len(result) == 1
        assert "name" not in result[0]
        assert result[0]["tool_call_id"] == "tc1"
        assert result[0]["content"] == "data"

    def test_no_excluded_keys_preserves_name(self):
        from comobot.providers.litellm_provider import _strip_non_standard_keys

        messages = [
            {"role": "tool", "tool_call_id": "tc1", "name": "read_file", "content": "data"},
        ]
        result = _strip_non_standard_keys(messages)
        assert result[0]["name"] == "read_file"

    def test_extra_and_excluded_keys_combined(self):
        from comobot.providers.litellm_provider import _strip_non_standard_keys

        messages = [
            {
                "role": "assistant",
                "content": "hi",
                "thinking_blocks": [{"text": "..."}],
                "name": "bot",
            },
        ]
        result = _strip_non_standard_keys(
            messages,
            extra_keys=frozenset({"thinking_blocks"}),
            excluded_keys=frozenset({"name"}),
        )
        assert "thinking_blocks" in result[0]
        assert "name" not in result[0]


class TestLLMResponseErrorType:
    """Test LLMResponse error_type field."""

    def test_default_error_type_is_none(self):
        from comobot.providers.base import LLMResponse

        r = LLMResponse(content="hello")
        assert r.error_type is None

    def test_error_type_set(self):
        from comobot.providers.base import LLMResponse

        r = LLMResponse(
            content="error", finish_reason="error", error_type="content_safety"
        )
        assert r.error_type == "content_safety"
        assert r.finish_reason == "error"
