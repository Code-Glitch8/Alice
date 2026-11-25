#!/usr/bin/env python3
import json
import re

# Test case 1: Response with content: null (JSON null)
response1 = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "has_tool_calls": true}'
print("Test 1: Response with content: null")
print("Input:", repr(response1))

# Simulate _parse_ai_response
def _parse_ai_response(response):
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
        parsed = json.loads(response)
        # Check for new format with has_tool_calls flag
        if parsed.get("has_tool_calls") and parsed.get("tool_calls"):
            return {
                "tool_calls": parsed.get("tool_calls", []),
                "content": parsed.get("content")
            }
        return parsed
    except json.JSONDecodeError:
        return None

result = _parse_ai_response(response1)
print("Result:", result)
print("Has tool_calls:", "tool_calls" in result if result else False)
print()

# Test case 2: Response with content: "" (empty string)
response2 = '{"content": "", "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "has_tool_calls": true}'
print("Test 2: Response with content: '' (empty string)")
print("Input:", repr(response2))

result2 = _parse_ai_response(response2)
print("Result:", result2)
print()

# Test case 3: Markdown-fenced response with content: null
response3 = '```json\n{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}]}\n```'
print("Test 3: Markdown-fenced response with content: null")
print("Input:", repr(response3))

result3 = _parse_ai_response(response3)
print("Result:", result3)
print()

# Test case 4: Check what happens when we check "if tool_calls in parsed"
print("Test 4: Checking 'tool_calls' in parsed")
if result and "tool_calls" in result:
    print("  Has tool_calls: True")
    content = result.get("content")
    if content is None:
        content = ""
    print("  Content after None check:", repr(content))
else:
    print("  Has tool_calls: False")