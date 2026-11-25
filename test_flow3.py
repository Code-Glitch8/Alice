#!/usr/bin/env python3
import json
import re

# Test case: Response with escaped quotes in JSON
response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "has_tool_calls": true}'
print("Input:", repr(response))
print()

# Check if it parses as JSON
try:
    parsed = json.loads(response)
    print("JSON parsed successfully!")
    print("Parsed:", parsed)
except json.JSONDecodeError as e:
    print("JSON parse error:", e)