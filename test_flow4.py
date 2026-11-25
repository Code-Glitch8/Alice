#!/usr/bin/env python3
import json
import re

# The actual JSON string that should be produced by the adapter
# In Python, we need to escape the quotes properly for the outer JSON string
response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'
print("Input:", repr(response))
print()

# Check if it parses as JSON
try:
    parsed = json.loads(response)
    print("JSON parsed successfully!")
    print("Parsed:", parsed)
except json.JSONDecodeError as e:
    print("JSON parse error:", e)