#!/usr/bin/env python3
"""Test tool calling normalization from dict args to JSON string."""
import json

# Test the normalization logic that was added to _parse_response

def normalize_tool_calls(tool_calls):
    """Normalize tool calls to ensure arguments are JSON strings."""
    normalized_tool_calls = []
    for tc in tool_calls:
        if isinstance(tc, dict) and "function" in tc:
            func = tc.get("function", {})
            args = func.get("arguments", {})
            # Ensure arguments is a JSON string (OpenAI-compatible wire format)
            if isinstance(args, dict):
                args = json.dumps(args, ensure_ascii=False)
            normalized_tc = {
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {
                    "name": func.get("name"),
                    "arguments": args
                }
            }
            normalized_tool_calls.append(normalized_tc)
        else:
            normalized_tool_calls.append(tc)
    return normalized_tool_calls


def test_normalize_dict_args():
    """Test that dict args get normalized to JSON string."""
    tool_calls = [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": {"app_name": "notepad"}  # Dict, not JSON string
        }
    }]

    result = normalize_tool_calls(tool_calls)
    assert isinstance(result[0]["function"]["arguments"], str)
    assert result[0]["function"]["arguments"] == '{"app_name": "notepad"}'
    print("✓ Dict args normalized to JSON string")


def test_normalize_string_args():
    """Test that JSON string args are preserved."""
    tool_calls = [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": '{"app_name": "notepad"}'  # Already a JSON string
        }
    }]

    result = normalize_tool_calls(tool_calls)
    assert result[0]["function"]["arguments"] == '{"app_name": "notepad"}'
    print("✓ JSON string args preserved")


def test_full_serialization():
    """Test the full serialization flow matches what _parse_response does."""
    tool_calls = [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": {"app_name": "notepad"}  # Dict
        }
    }]

    normalized = normalize_tool_calls(tool_calls)
    result = {
        "content": None,
        "tool_calls": normalized,
        "has_tool_calls": True
    }
    serialized = json.dumps(result, ensure_ascii=False)

    # Verify it parses correctly
    parsed = json.loads(serialized)
    assert parsed["has_tool_calls"] is True
    assert len(parsed["tool_calls"]) == 1
    assert parsed["tool_calls"][0]["function"]["name"] == "open_app"
    assert parsed["tool_calls"][0]["function"]["arguments"] == '{"app_name": "notepad"}'
    print("✓ Full serialization flow works correctly")


def test_with_multiple_args():
    """Test with multiple tool calls."""
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "open_app",
                "arguments": {"app_name": "notepad"}
            }
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "type_text",
                "arguments": {"text": "Hello, world!"}
            }
        }
    ]

    normalized = normalize_tool_calls(tool_calls)
    serialized = json.dumps({"content": None, "tool_calls": normalized, "has_tool_calls": True})
    parsed = json.loads(serialized)

    assert parsed["tool_calls"][0]["function"]["arguments"] == '{"app_name": "notepad"}'
    assert parsed["tool_calls"][1]["function"]["arguments"] == '{"text": "Hello, world!"}'
    print("✓ Multiple tool calls normalized correctly")


def test_with_content_and_tool_calls():
    """Test case where both content and tool_calls are present."""
    tool_calls = [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": {"app_name": "chrome"}
        }
    }]

    normalized = normalize_tool_calls(tool_calls)
    result = {
        "content": "Let me open Chrome for you.",
        "tool_calls": normalized,
        "has_tool_calls": True
    }
    serialized = json.dumps(result, ensure_ascii=False)
    parsed = json.loads(serialized)

    assert parsed["content"] == "Let me open Chrome for you."
    assert parsed["tool_calls"][0]["function"]["arguments"] == '{"app_name": "chrome"}'
    print("✓ Content + tool_calls serialized correctly")


if __name__ == "__main__":
    test_normalize_dict_args()
    test_normalize_string_args()
    test_full_serialization()
    test_with_multiple_args()
    test_with_content_and_tool_calls()
    print("\n✓ All normalization tests passed!")