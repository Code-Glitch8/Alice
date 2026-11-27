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

print('_tool_schemas count:', len(ai_planner._tool_schemas))
print('Schema keys count:', len(ai_planner._tool_schemas))
if ai_planner._tool_schemas:
    print('First 3 schemas:')
    for k in list(ai_planner._tool_schemas.keys())[:3]:
        print(f'  {k}: {ai_planner._tool_schemas[k]}')
print()
print('SUCCESS: AIPlanner built', len(ai_planner._tool_schemas), 'schemas')