#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')

# Test import is working
from alice.core.application import AliceApplication
print('Import successful')

# Test instantiation with mock config
class MockAutomationConfig:
    auto_confirm_category_a = True
    require_confirm_category_b = False
    restricted_category_c = False
    max_tool_calls = 5
    allow_edit_files = True
    require_confirmation_for_destructive = True

class MockAIConfig:
    idle_timeout = 300

class MockConfig:
    automation = MockAutomationConfig()
    ai = MockAIConfig()
    context_manager = type('CM', (), {
        'max_tokens': 6000,
        'reserve_tokens': 2192,
        'model_name': 'qwen3.5-4b'
    })()

config = MockConfig()
app = AliceApplication(config)

print('AliceApplication created successfully')
print('model_detector:', app.model_detector)
print('context_manager:', app.context_manager)
print('ai_planner:', app.ai_planner)
print('tool_registry:', app.tool_registry)
print('tool_dispatcher:', app.tool_dispatcher)
print('tool_registry.tools count:', len(app.tool_registry.tools))
print('ai_planner._tool_schemas count:', len(app.ai_planner._tool_schemas))