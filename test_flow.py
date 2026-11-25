#!/usr/bin/env python3
import json
import re

# Simulate what _parse_response returns when there are tool_calls
tool_calls = [{'id': 'call_123', 'type': 'function', 'function': {'name': 'open_app', 'arguments': '{"app_name": "notepad"}'}}]
result = {
    'content': None,
    'tool_calls': tool_calls,
    'has_tool_calls': True
}
response = json.dumps(result, ensure_ascii=False)
print('Response from _parse_response:')
print(repr(response))
print()

# Now simulate what _parse_ai_response does
response_stripped = response.strip()

# Try raw JSON parsing
parsed = json.loads(response_stripped)
print('Parsed:')
print(parsed)
print()

# Check the logic
if parsed.get('has_tool_calls') and parsed.get('tool_calls'):
    output = {
        'tool_calls': parsed.get('tool_calls', []),
        'content': parsed.get('content')
    }
    print('After extraction:')
    print(output)
    print()
    print('tool_calls in output:', 'tool_calls' in output)
    print('tool_calls:', output['tool_calls'])
    print()
    # Check arguments
    tc = output['tool_calls'][0]
    print('First tool call function arguments:', tc['function']['arguments'])
    print('Arguments type:', type(tc['function']['arguments']))
    args = tc['function']['arguments']
    if isinstance(args, str):
        print('Parsing arguments as JSON string:')
        parsed_args = json.loads(args)
        print('Parsed args:', parsed_args)