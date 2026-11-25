#!/usr/bin/env python3
import json
import re

# Test the exact string that fails
test_string = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "content": ""}'

print("Input string repr:", repr(test_string))
print()

# Try json.loads directly
try:
    result = json.loads(test_string)
    print("Direct json.loads: SUCCESS")
    print("Result:", json.dumps(result, indent=2))
except json.JSONDecodeError as e:
    print("Direct json.loads: FAILED")
    print("Error:", e)
    print()

# Now test the _parse_ai_response method
from alice.core.application import AliceApplication
from unittest.mock import MagicMock, patch
from alice.ai.lmstudio_adapter import LMStudioAdapter

mock_config = MagicMock()
mock_config.ai.base_url = "http://127.0.0.1:1234"

with patch.object(LMStudioAdapter, '_request', return_value={}):
    app = AliceApplication(mock_config)

# Test 1: Raw JSON
print("Testing _parse_ai_response with raw JSON:")
result1 = app._parse_ai_response(test_string)
print(f"  Result: {result1}")

# Test 2: Check if the issue is in the markdown detection
print("\nTesting markdown detection:")
print(f"  Contains ```json: {'```json' in test_string}")
print(f"  Contains ```: {'```' in test_string}")

# The markdown regex would NOT match because there are no fences
# Let's trace through the code path
print("\n=== Tracing code path ===")
response = test_string.strip()
print(f"1. Response stripped: {repr(response[:50])}...")

# Check markdown condition
if "```json" in response or "```" in response:
    print("2. Markdown condition: True (would try markdown parsing)")
else:
    print("2. Markdown condition: False (would skip to raw JSON)")

# Raw JSON parsing
try:
    parsed = json.loads(response)
    print(f"3. Raw JSON parse: SUCCESS")
    print(f"   Parsed tool_calls count: {len(parsed.get('tool_calls', []))}")
except json.JSONDecodeError as e:
    print(f"3. Raw JSON parse: FAILED - {e}")