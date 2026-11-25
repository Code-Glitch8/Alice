#!/usr/bin/env python3
import json

# Test case 1: LM Studio returns arguments as a JSON string (OpenAI format)
lm_studio_with_string_args = {
    "choices": [{
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "open_app",
                    "arguments": '{"app_name": "notepad"}'  # String, not dict
                }
            }]
        }
    }]
}

print("Test 1: LM Studio returns arguments as JSON string")
choice = lm_studio_with_string_args.get("choices", [])[0]
message = choice.get("message", {})
tool_calls = message.get("tool_calls")
content = message.get("content")

result = {
    "content": content if content else None,
    "tool_calls": tool_calls,
    "has_tool_calls": True
}
serialized = json.dumps(result, ensure_ascii=False)
print("Serialized:", serialized)
print()

parsed = json.loads(serialized)
tc = parsed["tool_calls"][0]
print("Parsed arguments:", tc["function"]["arguments"])
print("Type:", type(tc["function"]["arguments"]))
print("Is string:", isinstance(tc["function"]["arguments"], str))
print()

# Test case 2: LM Studio returns arguments as a dict
lm_studio_with_dict_args = {
    "choices": [{
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "open_app",
                    "arguments": {"app_name": "notepad"}  # Dict
                }
            }]
        }
    }]
}

print("Test 2: LM Studio returns arguments as dict")
choice = lm_studio_with_dict_args.get("choices", [])[0]
message = choice.get("message", {})
tool_calls = message.get("tool_calls")
content = message.get("content")

result = {
    "content": content if content else None,
    "tool_calls": tool_calls,
    "has_tool_calls": True
}
serialized = json.dumps(result, ensure_ascii=False)
print("Serialized:", serialized)
print()

parsed = json.loads(serialized)
tc = parsed["tool_calls"][0]
print("Parsed arguments:", tc["function"]["arguments"])
print("Type:", type(tc["function"]["arguments"]))