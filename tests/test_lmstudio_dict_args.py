#!/usr/bin/env python3
"""Test LM Studio returning tool calls with dict arguments (native API format)."""
import json
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.core.config import Config


def test_chat_with_dict_args_from_lm_studio():
    """
    Test when LM Studio native API returns tool calls with dict arguments.

    This is the critical test that verifies the normalization fix works correctly.
    When tools are sent to LM Studio via the native API, it may return arguments
    as Python dict objects instead of JSON strings. The _parse_response method
    must normalize these to JSON strings for ALICE's tool execution system.
    """
    config = Config()
    config.ai.base_url = "http://127.0.0.1:1234"
    config.ai.auto_start_server = False

    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"

    # Simulate LM Studio native API returning tool calls with dict arguments
    # This happens when tools are passed to the /v1/chat/completions endpoint
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "open_app",
                        "arguments": {"app_name": "notepad"}  # Dict, NOT string!
                    }
                }]
            }
        }]
    }

    # Call chat - this should normalize the dict args to JSON string
    answer = adapter.chat([{"role": "user", "content": "Open notepad"}])

    print("Raw answer from adapter.chat():")
    print(repr(answer))
    print()

    # Parse the result
    parsed = json.loads(answer)
    print("Parsed result:")
    print(json.dumps(parsed, indent=2))
    print()

    # Verify structure
    assert "has_tool_calls" in parsed, "has_tool_calls flag missing"
    assert parsed["has_tool_calls"] is True, "has_tool_calls should be true"
    assert "tool_calls" in parsed, "tool_calls missing"
    assert len(parsed["tool_calls"]) == 1, "Should have 1 tool call"

    tc = parsed["tool_calls"][0]
    assert tc["function"]["name"] == "open_app", "Function name should be open_app"

    # The critical check: arguments should be a JSON string (OpenAI-compatible format)
    args = tc["function"]["arguments"]
    print(f"Arguments type: {type(args).__name__}")
    print(f"Arguments value: {args}")

    assert isinstance(args, str), f"Arguments should be a string, got {type(args).__name__}"

    # Verify the arguments can be parsed as JSON
    parsed_args = json.loads(args)
    assert parsed_args == {"app_name": "notepad"}, f"Expected {{'app_name': 'notepad'}}, got {parsed_args}"

    print()
    print("✓ Test passed! Arguments correctly normalized from dict to JSON string")

    return True


def test_chat_with_multiple_tool_calls_dict_args():
    """Test with multiple tool calls - some with dict args, some with string args."""
    config = Config()
    adapter = LMStudioAdapter(config)
    adapter.model_loaded = True
    adapter.current_model = "qwen-test"

    # Mix of dict and string arguments (edge case)
    adapter._request = lambda *_args, **_kwargs: {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "open_app",
                            "arguments": {"app_name": "notepad"}  # Dict
                        }
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "type_text",
                            "arguments": '{"text": "Hello, world!"}'  # String
                        }
                    }
                ]
            }
        }]
    }

    answer = adapter.chat([{"role": "user", "content": "Open notepad and write hello"}])
    parsed = json.loads(answer)

    assert len(parsed["tool_calls"]) == 2

    # First call: dict args normalized to string
    tc1 = parsed["tool_calls"][0]
    assert isinstance(tc1["function"]["arguments"], str)
    assert json.loads(tc1["function"]["arguments"]) == {"app_name": "notepad"}

    # Second call: string args preserved
    tc2 = parsed["tool_calls"][1]
    assert tc2["function"]["arguments"] == '{"text": "Hello, world!"}'

    print("✓ Multiple tool calls test passed!")
    return True


if __name__ == "__main__":
    test_chat_with_dict_args_from_lm_studio()
    print()
    test_chat_with_multiple_tool_calls_dict_args()
    print()
    print("=" * 60)
    print("All LM Studio dict args tests passed!")
    print("=" * 60)