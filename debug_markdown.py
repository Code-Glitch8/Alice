#!/usr/bin/env python3
import re
import json

# Test the exact string from test_alice.py line 264
response = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}, "content": ""}\n```'

print("Input string:")
print(repr(response))
print()

# Check if it has markdown fences
print("Has ```json:", "```json" in response)
print("Has ```:", "```" in response)
print()

# Apply the regex
match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
if match:
    content = match.group(1).strip()
    print("Extracted content:")
    print(repr(content))
    print()

    # Try to parse
    try:
        result = json.loads(content)
        print("Parse result: SUCCESS")
        print(result)
    except json.JSONDecodeError as e:
        print(f"Parse result: FAILED - {e}")
else:
    print("No match found!")