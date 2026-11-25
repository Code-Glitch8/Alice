#!/usr/bin/env python3
"""Test Notepad scenario end-to-end."""
import asyncio
import sys
sys.path.insert(0, '.')

from alice.core.application import AliceApplication
from alice.core.config import Config

async def test_notepad_scenario():
    """Test the Notepad scenario via execute_intent."""
    config = Config.load()
    app = AliceApplication(config)

    # Test the intent
    intent = "open notepad, type 'Hello from ALICE', save as test.txt on desktop"
    result = await app.execute_intent(intent)

    print(f"Intent: {intent}")
    print(f"Plan: {result.get('plan', 'N/A')}")

    all_verified = True
    for step in result.get('steps', []):
        verified = step.get('verified', False)
        status = "✓ VERIFIED" if verified else "✗ FAILED"
        print(f"Step {step.get('step_id')}: {step.get('description')} -> {status}")
        if not verified:
            all_verified = False

    print()
    if all_verified:
        print("SUCCESS: All steps verified!")
        return 0
    else:
        print("FAILURE: Some steps failed verification")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(test_notepad_scenario())
    sys.exit(exit_code)