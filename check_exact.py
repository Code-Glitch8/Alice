#!/usr/bin/env python3
import re

# Read the test file
with open('tests/test_alice.py', 'r') as f:
    content = f.read()

# Find line 264
lines = content.split('\n')
if len(lines) >= 264:
    line = lines[263]  # 0-indexed
    print("Line 264:")
    print(line)
    print()

    # Extract the response string
    match = re.search(r'response = (.*)', line)
    if match:
        response_repr = match.group(1).strip().rstrip(',')
        print("Response repr:")
        print(response_repr)
        print()

        # Try to evaluate it
        import ast
        try:
            response = ast.literal_eval(response_repr)
            print("Parsed response:")
            print(repr(response))
            print()

            # Now test parsing
            match2 = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
            if match2:
                content = match2.group(1).strip()
                print("Extracted content:")
                print(repr(content))
                print()

                import json
                try:
                    result = json.loads(content)
                    print("Parse: SUCCESS")
                    print(f"Result: {result}")
                except json.JSONDecodeError as e:
                    print(f"Parse: FAILED - {e}")
        except Exception as e:
            print(f"Eval error: {e}")