#!/usr/bin/env python3
import re

# Read the test file
with open('tests/test_alice.py', 'r') as f:
    lines = f.readlines()

# Print line 264 (index 263)
line_264 = lines[263]
print("Line 264 raw:")
print(repr(line_264))
print()

# Find the response string
# Look for the pattern
content = ''.join(lines)
match = re.search(r'response = (.*?)\n', content[content.find('test_parse_markdown_fenced_json'):content.find('test_parse_markdown_fenced_json')+500])
if match:
    print("Found response assignment:")
    print(repr(match.group(1)))
    print()

    # Extract the string
    import ast
    try:
        response_str = ast.literal_eval(match.group(1))
        print("Parsed response string:")
        print(repr(response_str))
    except:
        pass