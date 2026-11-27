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

# Debug: Check what _build_tool_schemas does
items = ai_planner._get_tool_registry_items()
print('Number of items:', len(items))
print()

for tool_name, tool_def in items.items():
    print(f'{tool_name}:')
    print(f'  type: {type(tool_def).__name__}')
    print(f'  callable: {callable(tool_def)}')
    print(f'  has __doc__: {hasattr(tool_def, "__doc__")}')
    print(f'  has schema: {hasattr(tool_def, "schema")}')
    print(f'  isinstance dict: {isinstance(tool_def, dict)}')
    if hasattr(tool_def, "__doc__"):
        print(f'  __doc__: {tool_def.__doc__[:100] if tool_def.__doc__ else None}')
    print()