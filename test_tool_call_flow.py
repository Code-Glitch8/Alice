#!/usr/bin/env python3
"""Test tool calling flow from AI adapter."""
import asyncio
import json
from alice.core.application import AliceApplication
from alice.core.config import Config

async def test_tool_call_flow():
    """Test the tool call flow that would happen when AI responds with tool calls."""
    config = Config.load()
    app = AliceApplication(config)

    # Simulate what happens when AI returns a tool call
    # The AI would return something like:
    tool_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "open_app",
                "arguments": '{"app": "notepad"}'  # AI uses 'app' not 'app_name'
            }
        }
    ]

    print("Testing tool call flow with AI-generated arguments...")
    print(f"Tool calls: {json.dumps(tool_calls, indent=2)}")

    # This is what happens in chat_with_tools -> _execute_tool_calls
    history = [{"role": "user", "content": "Open notepad"}]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def test_with_json_string_args():
    """Test with JSON string arguments that AI would send."""
    config = Config.load()
    app = AliceApplication(config)

    # Test with JSON string arguments (what AI sends)
    tool_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "open_app",
                "arguments": '{"app": "calculator"}'
            }
        }
    ]

    print("\n\nTesting with JSON string arguments...")
    print(f"Tool calls: {json.dumps(tool_calls, indent=2)}")

    history = [{"role": "user", "content": "Open calculator"}]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def test_with_dict_args():
    """Test with dict arguments (already parsed)."""
    config = Config.load()
    app = AliceApplication(config)

    # Test with dict arguments (some adapters might send this way)
    tool_calls = [
        {
            "id": "call_456",
            "type": "function",
            "function": {
                "name": "open_app",
                "arguments": {"app": "chrome"}
            }
        }
    ]

    print("\n\nTesting with dict arguments...")
    print(f"Tool calls: {json.dumps(tool_calls, indent=2)}")

    history = [{"role": "user", "content": "Open chrome"}]

    try:
        result = await app._execute_tool_calls(tool_calls, history)
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    await test_tool_call_flow()
    await test_with_json_string_args()
    await test_with_dict_args()

if __name__ == "__main__":
    asyncio.run(main())