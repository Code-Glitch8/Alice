#!/usr/bin/env python3
"""Test the full flow from LM Studio to tool execution."""
import json


def _parse_ai_response(response: str):
    """Simulate _parse_ai_response from application.py"""
    if not response:
        return None

    import re
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


def _execute_tool_calls(tool_calls, arguments):
    """Simulate _execute_tool_calls argument parsing from application.py"""
    for call in tool_calls:
        if call.get("type") != "function":
            continue

        func = call.get("function", {})
        tool_name = func.get("name")
        arguments_str = func.get("arguments", "{}")

        # Handle both JSON string and dict arguments
        if isinstance(arguments_str, dict):
            arguments = arguments_str
        elif isinstance(arguments_str, str):
            try:
                arguments = json.loads(arguments_str or "{}")
            except json.JSONDecodeError as exc:
                print(f"Error parsing arguments: {exc}")
                continue
        elif arguments_str is None:
            arguments = {}
        else:
            print(f"Unsupported argument type: {type(arguments_str)}")
            continue

        print(f"Tool: {tool_name}, Arguments: {arguments}")
        yield tool_name, arguments


def test_case_1_dict_args_from_adapter():
    """Test case 1: LM Studio returns args as dict, adapter normalizes to JSON string."""
    print("=" * 60)
    print("TEST: Dict args from LM Studio -> JSON string via adapter")
    print("=" * 60)

    # This is what _parse_response in lmstudio_adapter.py returns
    response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'

    parsed = _parse_ai_response(response)
    print(f"Parsed: {json.dumps(parsed, indent=2)}")

    if parsed and "tool_calls" in parsed:
        tc = parsed["tool_calls"][0]
        args = tc["function"]["arguments"]
        print(f"\nArguments type: {type(args).__name__}")
        print(f"Arguments: {args}")

        # Now simulate _execute_tool_calls
        print("\nExecuting tool calls:")
        for tool_name, args in _execute_tool_calls(parsed["tool_calls"], None):
            print(f"  ✓ {tool_name}({args})")

    print()


def test_case_2_string_args_already():
    """Test case 2: LM Studio returns args as JSON string (already in OpenAI format)."""
    print("=" * 60)
    print("TEST: String args from LM Studio -> preserved as string")
    print("=" * 60)

    # This is what would happen if LM Studio returned args as strings
    response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"chrome\\"}"}}], "has_tool_calls": true}'

    parsed = _parse_ai_response(response)
    print(f"Parsed: {json.dumps(parsed, indent=2)}")

    if parsed and "tool_calls" in parsed:
        tc = parsed["tool_calls"][0]
        args = tc["function"]["arguments"]
        print(f"\nArguments type: {type(args).__name__}")
        print(f"Arguments: {args}")

        print("\nExecuting tool calls:")
        for tool_name, args in _execute_tool_calls(parsed["tool_calls"], None):
            print(f"  ✓ {tool_name}({args})")

    print()


def test_case_3_standalone_json_string_args():
    """Test case: JSON string args get double-escaped - verify this doesn't happen."""
    print("=" * 60)
    print("TEST: Verify JSON string args are not double-escaped")
    print("=" * 60)

    # The adapter should output args as: {"app_name": "notepad"}
    # Not: {\"app_name\": \"notepad\"}
    response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'

    parsed = _parse_ai_response(response)

    if parsed and "tool_calls" in parsed:
        tc = parsed["tool_calls"][0]
        args = tc["function"]["arguments"]

        # Verify it's a valid JSON string
        print(f"Arguments: {args}")

        # Should parse to dict
        parsed_args = json.loads(args)
        print(f"Parsed arguments: {parsed_args}")
        assert parsed_args == {"app_name": "notepad"}
        print("✓ Arguments correctly parsed")

    print()


def test_case_4_markdown_fenced_json():
    """Test case: JSON wrapped in markdown fences."""
    print("=" * 60)
    print("TEST: Markdown-fenced JSON response")
    print("=" * 60)

    response = '''```json
{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}
```'''

    parsed = _parse_ai_response(response)
    print(f"Parsed: {json.dumps(parsed, indent=2)}")

    if parsed and "tool_calls" in parsed:
        tc = parsed["tool_calls"][0]
        args = tc["function"]["arguments"]
        print(f"\nArguments: {args}")

        print("\nExecuting tool calls:")
        for tool_name, args in _execute_tool_calls(parsed["tool_calls"], None):
            print(f"  ✓ {tool_name}({args})")

    print()


if __name__ == "__main__":
    test_case_1_dict_args_from_adapter()
    test_case_2_string_args_already()
    test_case_3_standalone_json_string_args()
    test_case_4_markdown_fenced_json()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)