#!/usr/bin/env python3
import re

# Read the test file and find the exact string
with open('tests/test_alice.py', 'r') as f:
    content = f.read()

# Find line 264
lines = content.split('\n')
if len(lines) >= 264:
    print("Line 264:")
    print(repr(lines[263]))

# Also search for the pattern
pattern = r"response = ('.*?')"
match = re.search(pattern, content[content.find('test_parse_markdown_fenced_json'):content.find('test_parse_markdown_fenced_json')+500])
if match:
    print("\nFound response assignment:")
    print(repr(match.group(1)))