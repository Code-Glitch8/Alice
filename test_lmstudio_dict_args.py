#!/usr/bin/env python3
"""Test LM Studio returning tool calls with dict arguments (native API format)."""
import json
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.core.config import Config


def test_chat_with_dict_args():
    """Test when LM Studio native API returns arguments as dict."""
    config = Config()
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
    print("✓ Test passed! Arguments correctly normalized to JSON string")


if __name__ == "__main__":
    test_chat_with_dict_args()