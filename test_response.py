#!/usr/bin/env python3
import json
import re

# Test string from line 264 - what I think it SHOULD be
response_correct = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}`\n```'

print('Test with CORRECT JSON:')
print(repr(response_correct))
print()

match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_correct, re.DOTALL)
if match:
    content = match.group(1).strip()
    print('Extracted content:')
    print(repr(content))
    print()

    try:
        result = json.loads(content)
        print('Parse: SUCCESS')
        print(result)
    except json.JSONDecodeError as e:
        print('Parse: FAILED -', e)

print()
print('='*60)
print()

# Test string from line 264 - what's actually in the file
response_actual = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}, "content": ""}\n```'

print('Test with ACTUAL JSON from file:')
print(repr(response_actual))
print()

match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_actual, re.DOTALL)
if match:
    content = match.group(1).strip()
    print('Extracted content:')
    print(repr(content))
    print()

    try:
        result = json.loads(content)
        print('Parse: SUCCESS')
        print(result)
    except json.JSONDecodeError as e:
        print('Parse: FAILED -', e)