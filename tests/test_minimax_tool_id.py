"""
Test MiniMax tool call ID handling.

This test verifies the complete flow:
1. LLM returns a tool call with MiniMax-assigned ID
2. We store the assistant message with tool_calls
3. We store the tool result with matching tool_call_id
4. Next LLM call includes both messages
5. LLM processes them correctly

Key question: does the tool_call_id survive the full round-trip?
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_llm_provider():
    """Create a LiteLLM provider configured for MiniMax."""
    from comobot.providers.litellm_provider import LiteLLMProvider

    provider = LiteLLMProvider(
        api_key="test-key",
        default_model="minimax/MiniMax-M2.1",
    )
    return provider


def make_minimax_tool_call_response(tool_call_id: str, tool_name: str, tool_args: str):
    """Create a fake LiteLLM response with a MiniMax-style tool call."""
    from litellm.types.utils import ChatCompletionMessageToolCall

    tc = ChatCompletionMessageToolCall(
        id=tool_call_id,
        type="function",
        function={"name": tool_name, "arguments": tool_args},
    )

    class FakeMessage:  # noqa: N801
        def __init__(self):
            self.content = "Calling tool..."
            self.role = "assistant"
            self.reasoning_content = None
            self.thinking_blocks = None
            self.tool_calls = [tc]

    class FakeChoice:
        def __init__(self):
            self.index = 0
            self.finish_reason = "tool_calls"
            self.message = FakeMessage()

    class FakeUsage:
        def __init__(self):
            self.prompt_tokens = 100
            self.completion_tokens = 50
            self.total_tokens = 150

    class FakeResponse:
        def __init__(self):
            self.choices = [FakeChoice()]
            self.usage = FakeUsage()

    return FakeResponse()


def make_final_response(text: str):
    """Create a fake final response without tool calls."""

    class FakeMessage:  # noqa: N801
        def __init__(self):
            self.content = text
            self.role = "assistant"
            self.reasoning_content = None
            self.thinking_blocks = None
            self.tool_calls = None

    class FakeChoice:
        def __init__(self):
            self.index = 0
            self.finish_reason = "stop"
            self.message = FakeMessage()

    class FakeUsage:
        def __init__(self):
            self.prompt_tokens = 100
            self.completion_tokens = 30
            self.total_tokens = 130

    class FakeResponse:
        def __init__(self):
            self.choices = [FakeChoice()]
            self.usage = FakeUsage()

    return FakeResponse()


@pytest.mark.asyncio
async def test_tool_call_id_preserved_in_history(mock_llm_provider):
    """Verify tool_call_id is correctly stored and retrieved from message history."""

    provider = mock_llm_provider

    # Initial messages
    messages = [
        {"role": "user", "content": "Read test.txt"},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]

    # Turn 1: MiniMax returns a tool call
    minimax_id = "call_function_abc123_1"
    fake_resp = make_minimax_tool_call_response(minimax_id, "read_file", '{"path": "test.txt"}')

    with patch(
        "comobot.providers.litellm_provider.acompletion",
        new_callable=AsyncMock,
    ) as mock_acompletion:
        mock_acompletion.return_value = fake_resp

        response = await provider.chat(
            messages=messages,
            tools=tools,
            model="minimax/MiniMax-M2.1",
        )

    assert response.has_tool_calls
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == minimax_id
    assert response.tool_calls[0].name == "read_file"

    # Turn 1: Simulate what the agent loop does
    assistant_msg = {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in response.tool_calls
        ],
    }

    tool_result_msg = {
        "role": "tool",
        "tool_call_id": response.tool_calls[0].id,
        "name": "read_file",
        "content": "File content: hello world",
    }

    # Verify tool result has correct ID
    assert tool_result_msg["tool_call_id"] == minimax_id

    # Turn 2: User sends "hi" with history
    messages_turn2 = messages + [assistant_msg, tool_result_msg, {"role": "user", "content": "hi"}]

    # Verify the tool_call_id in history
    tool_result_in_history = messages_turn2[2]
    assert tool_result_in_history["role"] == "tool"
    assert tool_result_in_history["tool_call_id"] == minimax_id

    # Turn 2: MiniMax returns a final response (no tools)
    fake_resp_turn2 = make_final_response("Hello! I read the file for you.")

    with patch(
        "comobot.providers.litellm_provider.acompletion",
        new_callable=AsyncMock,
    ) as mock_acompletion:
        mock_acompletion.return_value = fake_resp_turn2

        response2 = await provider.chat(
            messages=messages_turn2,
            tools=None,
            model="minimax/MiniMax-M2.1",
        )

    assert not response2.has_tool_calls
    assert "hello" in response2.content.lower() or "file" in response2.content.lower()


@pytest.mark.asyncio
async def test_multiple_tool_calls_same_turn(mock_llm_provider):
    """Test when MiniMax makes multiple tool calls in same response."""
    from litellm.types.utils import ChatCompletionMessageToolCall

    provider = mock_llm_provider

    messages = [{"role": "user", "content": "Find and read the config file"}]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_dir",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
    ]

    # Two tool calls
    tc1 = ChatCompletionMessageToolCall(
        id="call_function_list1_1",
        type="function",
        function={"name": "list_dir", "arguments": '{"path": "."}'},
    )
    tc2 = ChatCompletionMessageToolCall(
        id="call_function_read1_1",
        type="function",
        function={"name": "read_file", "arguments": '{"path": "config.json"}'},
    )

    class FakeMessage:  # noqa: N801
        def __init__(self):
            self.content = "Let me find and read that..."
            self.role = "assistant"
            self.reasoning_content = None
            self.thinking_blocks = None
            self.tool_calls = [tc1, tc2]

    class FakeChoice:
        def __init__(self):
            self.index = 0
            self.finish_reason = "tool_calls"
            self.message = FakeMessage()

    class FakeResponse:
        def __init__(self):
            self.choices = [FakeChoice()]
            self.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)

    with patch(
        "comobot.providers.litellm_provider.acompletion",
        new_callable=AsyncMock,
    ) as mock_acompletion:
        mock_acompletion.return_value = FakeResponse()

        response = await provider.chat(
            messages=messages,
            tools=tools,
            model="minimax/MiniMax-M2.1",
        )

    assert response.has_tool_calls
    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].id == "call_function_list1_1"
    assert response.tool_calls[1].id == "call_function_read1_1"

    # Verify tool results maintain correct IDs
    tool_result_1 = {
        "role": "tool",
        "tool_call_id": "call_function_list1_1",
        "name": "list_dir",
        "content": "file1.py\nfile2.py",
    }
    tool_result_2 = {
        "role": "tool",
        "tool_call_id": "call_function_read1_1",
        "name": "read_file",
        "content": '{"setting": true}',
    }

    assert tool_result_1["tool_call_id"] == "call_function_list1_1"
    assert tool_result_2["tool_call_id"] == "call_function_read1_1"


@pytest.mark.asyncio
async def test_system_to_user_conversion_preserves_tool_calls(mock_llm_provider):
    """Test that system->user conversion doesn't affect tool call messages."""
    from comobot.providers.litellm_provider import _convert_system_to_user

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Hi!",
            "tool_calls": [
                {
                    "id": "call_function_test_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_function_test_1",
            "name": "search",
            "content": "result",
        },
    ]

    converted = _convert_system_to_user(messages)

    # System should become user
    assert converted[0]["role"] == "user"
    assert "helpful assistant" in converted[0]["content"]

    # Tool call and tool result should be unchanged
    assert converted[2]["role"] == "assistant"
    assert converted[2]["tool_calls"][0]["id"] == "call_function_test_1"
    assert converted[3]["role"] == "tool"
    assert converted[3]["tool_call_id"] == "call_function_test_1"


@pytest.mark.asyncio
async def test_tool_result_message_format(mock_llm_provider):
    """Verify the tool result message has all required fields for MiniMax."""
    provider = mock_llm_provider

    messages = [
        {"role": "user", "content": "Hi"},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]

    minimax_id = "call_function_echo123_1"
    fake_resp = make_minimax_tool_call_response(minimax_id, "echo", '{"text": "hello"}')

    with patch(
        "comobot.providers.litellm_provider.acompletion",
        new_callable=AsyncMock,
    ) as mock_acompletion:
        mock_acompletion.return_value = fake_resp
        response = await provider.chat(messages=messages, tools=tools, model="minimax/MiniMax-M2.1")

    # Build tool result like the agent loop does
    tool_result = {
        "role": "tool",
        "tool_call_id": response.tool_calls[0].id,
        "name": response.tool_calls[0].name,
        "content": "echo: hello",
    }

    # Verify required fields for MiniMax API
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == minimax_id
    assert tool_result["name"] == "echo"
    assert "content" in tool_result

    # After adaptation (shouldn't change tool messages)
    from comobot.providers.base import LLMProvider
    from comobot.providers.litellm_provider import (
        _convert_system_to_user,
        _merge_consecutive_same_role,
        _strip_non_standard_keys,
    )

    adapted = LLMProvider._sanitize_empty_content([tool_result])
    adapted = _convert_system_to_user(adapted)
    adapted = _merge_consecutive_same_role(adapted)
    adapted = _strip_non_standard_keys(adapted)

    assert len(adapted) == 1
    assert adapted[0]["role"] == "tool"
    assert adapted[0]["tool_call_id"] == minimax_id
