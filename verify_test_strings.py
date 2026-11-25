#!/usr/bin/env python3
"""Verify the test strings are valid JSON."""
import json

# Test from line 246
test_246 = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{\\"x\\": 1}"}}], "content": "test"}'

print("Test line 246:")
print(f"  Python source: {repr(test_246)}")
print(f"  Actual string: {test_246}")

# This string contains: {"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{\\"x\\": 1}"}}], "content": "test"}
# The \\" in Python source becomes \" in the actual string
# So arguments = "{\\"x\\": 1}" becomes {"x": 1} after JSON parsing

try:
    result = json.loads(test_246)
    print(f"  Parse: SUCCESS")
    args = result['tool_calls'][0]['function']['arguments']
    print(f"  Arguments type: {type(args)}, value: {args}")
except json.JSONDecodeError as e:
    print(f"  Parse: FAILED - {e}")

print()

# Test from line 264
test_264 = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}, "content": ""}\n```'

print("Test line 264:")
print(f"  Python source: {repr(test_264)}")
print(f"  Actual string: {test_264}")

# Extract JSON from markdown
import re
match = re.search(r'```(?:json)?\s*(.*?)\s*```', test_264, re.DOTALL)
if match:
    json_str = match.group(1).strip()
    print(f"  Extracted JSON: {json_str}")
    try:
        result = json.loads(json_str)
        print(f"  Parse: SUCCESS")
        print(f"  Result: {result}")
    except json.JSONDecodeError as e:
        print(f"  Parse: FAILED - {e}")