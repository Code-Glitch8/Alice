#!/usr/bin/env python3
import json

# Simulate what comes from LM Studio API
lm_studio_response = {
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
                    "arguments": {"app_name": "notepad"}  # Dict, not JSON string
                }
            }]
        }
    }]
}

# Extract as _parse_response does
choice = lm_studio_response.get("choices", [])[0]
message = choice.get("message", {})
tool_calls = message.get("tool_calls")
content = message.get("content")

print("tool_calls:", tool_calls)
print("type of arguments:", type(tool_calls[0]["function"]["arguments"]))
print("arguments:", tool_calls[0]["function"]["arguments"])
print()

# What _parse_response does when there are tool_calls
if tool_calls:
    result = {
        "content": content if content else None,
        "tool_calls": tool_calls,
        "has_tool_calls": True
    }
    serialized = json.dumps(result, ensure_ascii=False)
    print("Serialized result:")
    print(repr(serialized))
    print()

    # Now check what _parse_ai_response does
    parsed = json.loads(serialized)
    print("Parsed back:")
    print(parsed)
    print()

    # Check the tool_calls
    tc = parsed["tool_calls"][0]
    print("Tool call function arguments:")
    print(tc["function"]["arguments"])
    print("Type:", type(tc["function"]["arguments"]))