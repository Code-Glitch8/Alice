#!/usr/bin/env python3
import json
import re

# The exact response that should trigger tool calling
response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "has_tool_calls": true}'

print("Input response:")
print(repr(response))
print()

# Check if it has markdown fences
print("Has ```json:", "```json" in response)
print("Has ```:", "```" in response)
print()

# Try to parse as JSON
try:
    parsed = json.loads(response)
    print("Parsed as JSON:")
    print(parsed)
    print()

    # Check has_tool_calls
    has_tool_calls = parsed.get("has_tool_calls")
    tool_calls = parsed.get("tool_calls")
    print("has_tool_calls:", has_tool_calls)
    print("tool_calls:", tool_calls)
    print()

    # The condition in _parse_ai_response
    if has_tool_calls and tool_calls:
        print("Condition met! Should return the extracted dict.")
    else:
        print("Condition NOT met!")

except json.JSONDecodeError as e:
    print("JSON parse error:", e)