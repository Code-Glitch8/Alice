#!/usr/bin/env python3
import json

# In a Python string literal:
# \\ -> becomes \ in the actual string
# \" -> becomes " in the actual string
# \\" -> becomes \" in the actual string

# To have a JSON string value like: {"app_name": "notepad"}
# The JSON must have: "arguments": "{\"app_name\": \"notepad\"}"
# In Python source, this needs to be: "arguments": "{\\"app_name\\": \\"notepad\\"}}"

# Test various forms
tests = [
    # Form 1: Two backslashes before quote -> \" in string -> " in JSON (WRONG - quote not escaped)
    ('Two backslash-quote', r'{"arguments": "{\\\"app_name\\\": \\\"notepad\\\"}"}'),

    # Form 2: Four backslashes -> \\ in string -> \ in JSON -> \" in final JSON (WRONG)
    ('Four backslash-quote', r'{"arguments": "{\\\\\"app_name\\\\\": \\\\\"notepad\\\\\"}"}'),

    # Form 3: What we want - valid JSON string
    ('What JSON needs', '{"arguments": "{\\"app_name\\": \\"notepad\\"}"}'),
]

for name, test in tests:
    print(f"{name}:")
    print(f"  Python source: {repr(test)}")
    try:
        result = json.loads(test)
        print(f"  JSON parse: SUCCESS")
        print(f"  arguments value: {result.get('arguments')}")
    except json.JSONDecodeError as e:
        print(f"  JSON parse: FAILED - {e}")
    print()

# Now let's understand what the actual JSON string should be
print("=== The Correct Approach ===")
print()
print("If LM Studio returns JSON that looks like:")
print('  {"tool_calls": [{"function": {"arguments": {"app_name": "notepad"}}}]}')
print()
print("When serialized to a JSON response, arguments as a DICT becomes:")
print('  {"tool_calls": [{"function": {"arguments": {"app_name": "notepad"}}}]}')
print()
print("But if LM Studio sends OpenAI-compatible format where arguments is a JSON STRING,")
print("the raw string BEFORE JSON serialization is:")
print('  {"tool_calls": [{"function": {"arguments": "{\\"app_name\\": \\"notepad\\"}"}}}]')
print()
print("To test this in Python source, we need to escape for BOTH Python AND JSON:")
test_correct = '{"tool_calls": [{"function": {"arguments": "{\\"app_name\\": \\"notepad\\"}"}}]}'
print(f"  Python source: {repr(test_correct)}")
try:
    result = json.loads(test_correct)
    print(f"  JSON parse: SUCCESS")
    print(f"  arguments type: {type(result['tool_calls'][0]['function']['arguments'])}")
    print(f"  arguments value: {result['tool_calls'][0]['function']['arguments']}")
except json.JSONDecodeError as e:
    print(f"  JSON parse: FAILED - {e}")