#!/usr/bin/env python3
import json

# The WRONG way - what we currently have
wrong = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "content": ""}'

# The CORRECT way - with escaped backslashes for Python to produce valid JSON
correct = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "content": ""}'

print("Wrong string (what appears in source):")
print("  repr:", repr(wrong))
print("  Parsed value at arguments:", wrong.split('"arguments": "')[1].split('"')[0] if '"arguments": "' in wrong else "N/A")
try:
    result = json.loads(wrong)
    print("  json.loads: SUCCESS")
except json.JSONDecodeError as e:
    print("  json.loads: FAILED -", e)

print()

print("Correct string (what it should be):")
print("  repr:", repr(correct))
print("  Parsed value at arguments:", correct.split('"arguments": "')[1].split('"')[0] if '"arguments": "' in correct else "N/A")
try:
    result = json.loads(correct)
    print("  json.loads: SUCCESS")
    print("  Parsed arguments:", result['tool_calls'][0]['function']['arguments'])
except json.JSONDecodeError as e:
    print("  json.loads: FAILED -", e)

print()
print("=== The issue ===")
print("In Python source code:")
print("  \"{\\\"app_name\\\": \\\"notepad\\\"}\" -> becomes -> {\"app_name\": \"notepad\"} -> NOT valid JSON")
print("  \"{\\\\\"app_name\\\\\": \\\\\"notepad\\\\\"}\" -> becomes -> {\"app_name\": \"notepad\"} -> VALID JSON")
print()
print("The problem: We need FOUR backslashes in Python to get TWO backslashes in the string,")
print("which become ONE backslash in JSON, escaping the inner quotes.")