#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')

from alice.tools.tools import create_default_tools
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.context_manager import ContextManager
from alice.ai.model_capability import create_model_detector
from alice.planner.ai_planner import AIPlanner

# Create tool registry
tool_registry = create_default_tools()
print("ToolRegistry type:", type(tool_registry))
print("ToolRegistry.tools count:", len(tool_registry.tools))

# Create context manager
config = type('Config', (), {
    'context_manager': type('CM', (), {
        'max_tokens': 6000,
        'reserve_tokens': 2192,
        'model_name': 'qwen3.5-4b'
    })()
})()

context_manager = ContextManager(
    max_context_tokens=6000,
    reserve_tokens=2192,
    system_prompt_tokens=1500,
    model_name='qwen3.5-4b',
)

# Create LMStudioAdapter
lmstudio_adapter = LMStudioAdapter(config)
print("LMStudioAdapter created")

# Create AIPlanner with ToolRegistry
ai_planner = AIPlanner(
    tool_registry=tool_registry,
    model_adapter=lmstudio_adapter,
    context_manager=context_manager,
)

print("AIPlanner created successfully")
print("_tool_schemas count:", len(ai_planner._tool_schemas))
print()
print("Schema keys:", list(ai_planner._tool_schemas.keys())[:5])