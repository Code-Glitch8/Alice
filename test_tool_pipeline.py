#!/usr/bin/env python3
"""Test the complete tool execution pipeline."""
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

print("=== Testing Complete Tool Execution Pipeline ===\n")

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.tools.tools import create_default_tools, ToolDispatcher

# Mock config
mock_config = MagicMock()
mock_config.ai.base_url = "http://127.0.0.1:1234"
mock_config.automation = MagicMock()
mock_config.automation.auto_confirm_category_a = True
mock_config.automation.require_confirm_category_b = False
mock_config.automation.restricted_category_c = False
mock_config.automation.max_tool_calls = 5

with patch.object(LMStudioAdapter, '_request', return_value={}):
    app = AliceApplication(mock_config)

# Test 1: Parse raw JSON with tool_calls
print("Test 1: Parse raw JSON with tool_calls")
response1 = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {"app_name": "notepad"}}}], "content": ""}'
result1 = app._parse_ai_response(response1)
print(f"  Result: {result1 is not None}")
print(f"  Has tool_calls: {'tool_calls' in result1 if result1 else False}")
if result1:
    print(f"  tool_calls: {result1['tool_calls']}")

# Test 2: Parse markdown-fenced JSON
print("\nTest 2: Parse markdown-fenced JSON")
response2 = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}\n```'
print(f"  Input: {repr(response2[:80])}...")
result2 = app._parse_ai_response(response2)
print(f"  Result: {result2 is not None}")
if result2:
    print(f"  Has tool_calls: {'tool_calls' in result2}")

# Test 3: Parse JSON with escaped arguments (OpenAI format)
print("\nTest 3: Parse JSON with escaped arguments (OpenAI format)")
response3 = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "content": ""}'
print(f"  Input: {repr(response3[:80])}...")
result3 = app._parse_ai_response(response3)
print(f"  Result: {result3 is not None}")
if result3:
    args = result3['tool_calls'][0]['function']['arguments']
    print(f"  Arguments type: {type(args)}, value: {args}")

# Test 4: Tool dispatcher execution
print("\nTest 4: Tool dispatcher execution")
dispatcher = ToolDispatcher(create_default_tools(), mock_config)

# Test executing a valid tool
tool_result = dispatcher.execute("open_app", {"app_name": "notepad"})
print(f"  open_app result: {tool_result}")

print("\n" + "="*60)
print("Checking the actual test from test_alice.py line 264:")
# Exact same as the test
test_response = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}\n```'
print(f"Test string: {repr(test_response)}")