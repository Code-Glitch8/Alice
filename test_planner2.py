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
print('Schema keys:', list(ai_planner._tool_schemas.keys())[:10])

# Check a specific schema
if 'open_app' in ai_planner._tool_schemas:
    print()
    print('open_app schema:', ai_planner._tool_schemas['open_app'])
else:
    print()
    print('open_app NOT in schemas')
    # Check what's in the _get_tool_registry_items
    items = ai_planner._get_tool_registry_items()
    print('Tool items keys:', list(items.keys())[:5])
    for name, tool_def in items.items():
        tname = type(tool_def).__name__
        has_s = hasattr(tool_def, "schema")
        print(f'{name}: type={tname}, has schema={has_s}')