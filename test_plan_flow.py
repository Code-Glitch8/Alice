#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')

from alice.tools.tools import create_default_tools
from alice.planner.ai_planner import AIPlanner

# Create tool registry
tool_registry = create_default_tools()

# Create AIPlanner - this should call _build_tool_schemas()
ai_planner = AIPlanner(
    tool_registry=tool_registry,
    model_adapter=None,
    context_manager=None,
)

# Test the plan method - it should handle no model adapter gracefully
result = ai_planner.plan("list installed applications")
print('Plan result:', result)

# Test validate_plan
valid = ai_planner.validate_plan(result)
print('Plan valid:', valid)

# Test with non-empty tool_registry check
print()
print('Tool registry in planner:', ai_planner.tool_registry is not None)
print('Number of tools in registry:', len(ai_planner.tool_registry.tools) if ai_planner.tool_registry else 0)
print('Number of schemas:', len(ai_planner._tool_schemas))