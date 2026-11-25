#!/usr/bin/env python3
"""Test tool execution flow."""
import asyncio
from alice.core.application import AliceApplication
from alice.core.config import Config

async def test():
    config = Config.load()
    app = AliceApplication(config)

    # Test execute_intent with 'open notepad'
    result = await app.execute_intent('open notepad')
    print('Result:', result)
    for step in result.get('steps', []):
        print(f"Step {step.get('step_id')}: {step.get('description')}")
        print(f"  Tool: {step.get('tool')}")
        print(f"  Params: {step.get('parameters')}")
        print(f"  Verified: {step.get('verified')}")
        if step.get('error'):
            print(f"  Error: {step.get('error')}")

asyncio.run(test())