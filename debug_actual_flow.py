#!/usr/bin/env python3
import json
from unittest.mock import MagicMock, patch

# Simulate what _parse_response does
print("=== Simulating LM Studio Response ===\n")

# Case 1: LM Studio returns tool_calls with arguments as a STRING (OpenAI format)
tool_calls_openai = [
    {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": json.dumps({"app_name": "notepad"})  # STRING
        }
    }
]

lm_response_openai = json.dumps({"tool_calls": tool_calls_openai, "content": ""}, ensure_ascii=False)
print("Case 1: OpenAI format (arguments as JSON string)")
print(f"  LM Studio output: {lm_response_openai}")
print()

# Case 2: LM Studio returns tool_calls with arguments as a DICT
tool_calls_decoded = [
    {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": {"app_name": "notepad"}  # DICT
        }
    }
]

lm_response_decoded = json.dumps({"tool_calls": tool_calls_decoded, "content": ""}, ensure_ascii=False)
print("Case 2: Decoded format (arguments as dict)")
print(f"  LM Studio output: {lm_response_decoded}")
print()

# Now test parsing each case
print("=== Testing _parse_ai_response ===\n")

# We need to avoid triggering the actual model loading
class MockApp:
    def _parse_ai_response(self, response):
        from alice.core.application import AliceApplication
        # We'll just test the parsing logic inline
        import re
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

app = MockApp()

print("Parsing Case 1 (OpenAI format):")
result1 = app._parse_ai_response(lm_response_openai)
print(f"  Result: {result1 is not None}")
if result1:
    print(f"  tool_calls: {result1['tool_calls']}")
    args = result1['tool_calls'][0]['function']['arguments']
    print(f"  arguments type: {type(args)}, value: {args}")

print()

print("Parsing Case 2 (Decoded format):")
result2 = app._parse_ai_response(lm_response_decoded)
print(f"  Result: {result2 is not None}")
if result2:
    print(f"  tool_calls: {result2['tool_calls']}")
    args = result2['tool_calls'][0]['function']['arguments']
    print(f"  arguments type: {type(args)}, value: {args}")

print()
print("=== The Real Issue ===")
print("When arguments is a dict in Python, json.dumps() creates:")
print('  "arguments": {"app_name": "notepad"}  <- valid JSON object')
print()
print("When arguments is a JSON string in Python, json.dumps() creates:")
print('  "arguments": "{\\"app_name\\": \\"notepad\\"}"  <- valid JSON with escaped string')
print()
print("Both should parse correctly with json.loads()")
print()
print("Let me verify both are valid JSON strings:")

# Verify both outputs are valid JSON strings
print(f"\n'{lm_response_openai[:50]}...' is valid JSON: ", end="")
try:
    json.loads(lm_response_openai)
    print("YES")
except json.JSONDecodeError as e:
    print(f"NO - {e}")

print(f"\n'{lm_response_decoded[:50]}...' is valid JSON: ", end="")
try:
    json.loads(lm_response_decoded)
    print("YES")
except json.JSONDecodeError as e:
    print(f"NO - {e}")