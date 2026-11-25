#!/usr/bin/env python3
"""Test CLI intent execution."""
import asyncio
import sys
sys.path.insert(0, '.')
from alice.core.application import AliceApplication
from alice.core.config import Config

async def test():
    config = Config.load()
    app = AliceApplication(config)
    result = await app.execute_intent("open notepad, type 'Hello from ALICE', save as test.txt on desktop")
    print('Plan:', result.get('plan', 'N/A'))
    for step in result.get('steps', []):
        print(f"Step {step.get('step_id')}: {step.get('description')} -> verified: {step.get('verified')}")

asyncio.run(test())