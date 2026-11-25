#!/usr/bin/env python3
"""Test AI tool call flow end-to-end."""
import asyncio
import json
from alice.core.application import AliceApplication
from alice.core.config import Config

async def test_ai_flow():
    """Test the complete AI-to-tool execution flow."""
    print("=" * 60)
    print("TEST: Complete AI-to-Tool Flow")
    print("=" * 60)

    config = Config.load()
    app = AliceApplication(config)

    # Test 1: Simulate AI sending tool call with 'app' parameter
    print("\n1. Simulating AI tool call with 'app' parameter:")
    tool_calls = [{
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": '{"app": "notepad"}'
        }
    }]

    history = [{"role": "user", "content": "Open notepad"}]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"   SUCCESS: {result[:100]}...")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 2: Simulate AI sending tool call with 'app_name' parameter
    print("\n2. Simulating AI tool call with 'app_name' parameter:")
    tool_calls = [{
        "id": "call_456",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": '{"app_name": "calculator"}'
        }
    }]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"   SUCCESS: {result[:100]}...")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 3: Test with dict arguments (some adapters might send this way)
    print("\n3. Simulating AI tool call with dict arguments:")
    tool_calls = [{
        "id": "call_789",
        "type": "function",
        "function": {
            "name": "open_app",
            "arguments": {"app": "chrome"}
        }
    }]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"   SUCCESS: {result[:100]}...")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 4: Test multiple tool calls in sequence
    print("\n4. Simulating multiple tool calls:")
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "open_app",
                "arguments": '{"app": "notepad"}'
            }
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "type_text",
                "arguments": '{"text": "Hello from ALICE"}'
            }
        }
    ]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"   SUCCESS: {result[:100]}...")
    except TypeError as e:
        print(f"   FAILED: {e}")

    print("\n" + "=" * 60)


async def test_all_app_tools():
    """Test all app-related tools (open, close, focus)."""
    print("\n" + "=" * 60)
    print("TEST: All App Tools with 'app' parameter")
    print("=" * 60)

    config = Config.load()
    app = AliceApplication(config)

    tools_to_test = [
        ("open_app", "notepad"),
        ("close_app", "notepad"),
        ("focus_app", "notepad"),
    ]

    for tool_name, app_name in tools_to_test:
        print(f"\nTesting {tool_name} with 'app' parameter:")
        tool_calls = [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": f'{{"app": "{app_name}"}}'
            }
        }]

        history = [{"role": "user", "content": f"Test {tool_name}"}]

        try:
            result = await app._execute_tool_calls(tool_calls, history)
            # Check if result contains error
            if "error" in result.lower():
                print(f"   ERROR in result: {result}")
            else:
                print(f"   SUCCESS")
        except TypeError as e:
            print(f"   FAILED: {e}")

    print("\n" + "=" * 60)


async def main():
    await test_ai_flow()
    await test_all_app_tools()

if __name__ == "__main__":
    asyncio.run(main())