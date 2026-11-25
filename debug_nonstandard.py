#!/usr/bin/env python3
import json
import re

# Test various non-standard AI responses
test_cases = [
    # Case 1: Proper JSON
    ("Proper JSON", '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}], "content": ""}'),

    # Case 2: Markdown-fenced JSON (proper)
    ("Markdown-fenced proper", '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}], "content": ""}\n```'),

    # Case 3: Plain text with JSON-like content (WRONG - not actual JSON)
    ("Plain text with JSON-like", 'Here is the tool call: {"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}], "content": ""}'),

    # Case 4: Markdown-fenced but with extra text inside
    ("Markdown with intro text", '```json\nHere are the tool calls:\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}], "content": ""}\n```'),

    # Case 5: Malformed JSON in markdown (extra bracket)
    ("Markdown malformed", '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}]}]\n```'),

    # Case 6: No content field
    ("No content field", '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}]}'),

    # Case 7: Content before tool calls
    ("Content first", '{"content": "Opening notepad...", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}}]}'),
]

def parse_ai_response(response):
    """Simulate the _parse_ai_response method."""
    if not response:
        return None

    response = response.strip()

    # Try markdown-fenced JSON first
    if "```json" in response or "```" in response:
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            content = match.group(1).strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

    # Try raw JSON parsing
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return None

print("=== Testing Various AI Response Formats ===\n")

for name, test in test_cases:
    print(f"Test: {name}")
    print(f"  Input: {test[:80]}...")
    result = parse_ai_response(test)
    if result:
        print(f"  Result: SUCCESS - {list(result.keys())}")
    else:
        print(f"  Result: FAILED (returned None)")
    print()