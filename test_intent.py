#!/usr/bin/env python3
"""Test intent execution directly."""
import sys
sys.path.insert(0, '.')

# Test the planner
from alice.planner.planner import TaskPlanner
from alice.tools.tools import create_default_tools

registry = create_default_tools()
planner = TaskPlanner(registry)

intent = "open notepad, type 'Hello from ALICE', save as test.txt on desktop"
print(f"Intent: {intent}")
print(planner.get_plan_summary())

steps = planner.plan(intent)
for step in steps:
    print(f"\nStep {step.step_id}: {step.description}")
    print(f"  Tool: {step.tool_name}")
    print(f"  Params: {step.parameters}")
    print(f"  Requires confirmation: {step.requires_confirmation}")

print("\n--- Executing steps ---")
for step in planner.execute_steps(registry):
    print(f"Step {step.step_id}: {step.description}")
    print(f"  Success: {step.error is None if step.result is None else True}")
    print(f"  Result: {step.result}")
    print(f"  Verified: {step.verified}")
    if step.error:
        print(f"  Error: {step.error}")