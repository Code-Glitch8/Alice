#!/usr/bin/env python3
"""Test to reproduce the bug 'got an unexpected keyword argument app'"""
import asyncio
import json
from alice.core.application import AliceApplication
from alice.core.config import Config
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.runtime_manager import RuntimeManager

async def test_full_chat_with_tool_calls():
    """Test the actual chat flow with tool calls."""
    print("=" * 60)
    print("TEST: Full chat flow with tool calls")
    print("=" * 60)

    config = Config.load()
    adapter = LMStudioAdapter(config)

    # Mock the adapter to return a tool call with 'app' parameter
    async def mock_chat(messages, **kwargs):
        # Simulate AI response with tool call using 'app' parameter
        return json.dumps({
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "open_app",
                        "arguments": '{"app": "notepad"}'
                    }
                }
            ]
        })

    manager = RuntimeManager(adapter, config)

    # Initialize without loading model
    await manager.start()

    # Patch the chat method to return our mock response
    original_chat = adapter.chat
    adapter.chat = lambda msgs, **kw: asyncio.to_thread(manager.adapter.chat, msgs, **kw)

    # Create the app
    app = AliceApplication(config)

    # Simulate chat_with_tools flow
    messages = [{"role": "system", "content": app.system_prompt},
                {"role": "user", "content": "Open notepad"}]

    print("\n1. Calling LLM to get response...")
    # We need to mock the response
    from unittest.mock import AsyncMock, patch

    # Mock the runtime chat to return tool calls
    tool_call_response = json.dumps({
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "open_app",
                    "arguments": '{"app": "notepad"}'
                }
            }
        ]
    })

    # Let's trace through the code manually
    print("\n2. Simulating _execute_tool_calls...")
    tool_calls = json.loads(tool_call_response).get("tool_calls", [])

    for call in tool_calls:
        if call.get("type") != "function":
            continue

        func = call.get("function", {})
        tool_name = func.get("name")
        arguments_str = func.get("arguments", "{}")
        call_id = call.get("id", "call_1")

        print(f"\n   Tool: {tool_name}, Arguments string: {arguments_str}")

        # Parse arguments
        if isinstance(arguments_str, str):
            arguments = json.loads(arguments_str)
        elif isinstance(arguments_str, dict):
            arguments = arguments_str
        else:
            arguments = {}

        print(f"   Parsed arguments: {arguments}")

        # Normalize arguments
        arguments = app._normalize_tool_arguments(tool_name, arguments)
        print(f"   Normalized arguments: {arguments}")

        # Get tool
        tool = app.tool_registry.get(tool_name)
        if tool:
            print(f"   Tool found: {tool.name}")

            # Execute tool
            try:
                result = tool.execute(**arguments)
                print(f"   Result: {result.get('status')} - {result.get('message')}")
            except TypeError as e:
                print(f"   ERROR: {e}")
                import traceback
                traceback.print_exc()

    await manager.stop()
    print("\n" + "=" * 60)


async def test_execute_intent_with_app_param():
    """Test execute_intent which uses TaskPlanner."""
    print("\n" + "=" * 60)
    print("TEST: execute_intent with 'open notepad'")
    print("=" * 60)

    config = Config.load()
    app = AliceApplication(config)

    result = await app.execute_intent("open notepad")
    print(f"\nPlan: {result.get('plan')}")
    for step in result.get('steps', []):
        print(f"Step {step.get('step_id')}: {step.get('description')}")
        print(f"  Tool: {step.get('tool')}")
        print(f"  Params: {step.get('parameters')}")
        print(f"  Verified: {step.get('verified')}")
        if step.get('error'):
            print(f"  Error: {step.get('error')}")


async def main():
    await test_full_chat_with_tool_calls()
    await test_execute_intent_with_app_param()

if __name__ == "__main__":
    asyncio.run(main())