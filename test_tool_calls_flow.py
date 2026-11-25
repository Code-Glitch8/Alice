#!/usr/bin/env python3
"""Test the tool calling flow end-to-end."""
import json

# Test the exact JSON response that LM Studio should return after normalization
# This is what _parse_response in lmstudio_adapter.py returns
response_json = {
    "content": None,
    "tool_calls": [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": json.dumps({"app_name": "notepad"}, ensure_ascii=False)  # JSON string, not dict
        }
    }],
    "has_tool_calls": True
}

# Serialize to string (this is what gets returned from adapter.chat)
serialized = json.dumps(response_json, ensure_ascii=False)
print("Serialized response:")
print(serialized)
print()

# Now test parsing in _parse_ai_response
def test_parse_ai_response(response):
    """Simulate _parse_ai_response from application.py"""
    if not response:
        return None

    response = response.strip()

    # Try markdown-fenced JSON first
    if "```json" in response or "```" in response:
        import re
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

result = test_parse_ai_response(serialized)
print("Parsed result:")
print(result)
print()

if result:
    print("✓ Successfully parsed!")
    print("  has_tool_calls:", result.get("has_tool_calls") if "has_tool_calls" in result else "handled via content/tool_calls keys")
    print("  tool_calls:", result.get("tool_calls"))
    print("  content:", result.get("content"))

    # Check arguments
    tc = result["tool_calls"][0]
    args = tc["function"]["arguments"]
    print("  arguments type:", type(args).__name__)
    print("  arguments:", args)
    print()

    # Test that we can parse arguments
    if isinstance(args, str):
        parsed_args = json.loads(args)
        print("  Parsed arguments:", parsed_args)
        print()
else:
    print("✗ Failed to parse!")
    exit(1)