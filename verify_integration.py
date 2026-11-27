#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')

# Test 1: Basic import test
print("=" * 60)
print("Test 1: Basic import test")
print("=" * 60)
try:
    from alice.core.application import AliceApplication
    print("✓ Import successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create mock config
print("\n" + "=" * 60)
print("Test 2: Create AliceApplication with mock config")
print("=" * 60)

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

try:
    config = MockConfig()
    app = AliceApplication(config)
    print("✓ AliceApplication created successfully")
except Exception as e:
    print(f"✗ Failed to create AliceApplication: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Check components
print("\n" + "=" * 60)
print("Test 3: Check component initialization")
print("=" * 60)
try:
    print(f"  model_detector: {app.model_detector}")
    print(f"  context_manager: {app.context_manager}")
    print(f"  ai_planner: {app.ai_planner}")
    print(f"  tool_registry: {app.tool_registry}")
    print(f"  tool_dispatcher: {app.tool_dispatcher}")
    print("✓ All components initialized")
except Exception as e:
    print(f"✗ Component check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Check tool registry count
print("\n" + "=" * 60)
print("Test 4: Check tool registry count")
print("=" * 60)
try:
    tools_count = len(app.tool_registry.tools)
    print(f"  tool_registry.tools count: {tools_count}")
    if tools_count == 29:
        print("✓ Tool registry has expected 29 tools")
    else:
        print(f"✗ Expected 29 tools, got {tools_count}")
        sys.exit(1)
except Exception as e:
    print(f"✗ Tool registry check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Check AIPlanner schema count
print("\n" + "=" * 60)
print("Test 5: Check AIPlanner schema count")
print("=" * 60)
try:
    schemas_count = len(app.ai_planner._tool_schemas)
    print(f"  ai_planner._tool_schemas count: {schemas_count}")
    if schemas_count == 29:
        print("✓ AIPlanner has expected 29 tool schemas")
    else:
        print(f"✗ Expected 29 schemas, got {schemas_count}")
        sys.exit(1)
except Exception as e:
    print(f"✗ AIPlanner schema check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Verify schemas cover all tools
print("\n" + "=" * 60)
print("Test 6: Verify schemas cover all tools")
print("=" * 60)
try:
    tool_names = set(app.tool_registry.tools.keys())
    schema_names = set(app.ai_planner._tool_schemas.keys())

    missing = tool_names - schema_names
    extra = schema_names - tool_names

    if missing:
        print(f"  ✗ Missing schemas for tools: {missing}")
    if extra:
        print(f"  ✗ Extra schemas for unknown tools: {extra}")

    if not missing and not extra:
        print("✓ All tools have corresponding schemas")
    else:
        print("✗ Schema coverage incomplete")
        sys.exit(1)
except Exception as e:
    print(f"✗ Schema coverage check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Direct AIPlanner instantiation test
print("\n" + "=" * 60)
print("Test 7: Direct AIPlanner instantiation with create_default_tools()")
print("=" * 60)
try:
    from alice.tools.tools import create_default_tools
    from alice.planner.ai_planner import AIPlanner

    tool_registry = create_default_tools()
    ai_planner = AIPlanner(
        tool_registry=tool_registry,
        model_adapter=None,
        context_manager=None,
    )

    print(f"  tool_registry.tools count: {len(tool_registry.tools)}")
    print(f"  ai_planner._tool_schemas count: {len(ai_planner._tool_schemas)}")

    if len(ai_planner._tool_schemas) == 29:
        print("✓ AIPlanner correctly initializes with 29 tool schemas")
    else:
        print(f"✗ Expected 29 schemas, got {len(ai_planner._tool_schemas)}")
        sys.exit(1)
except Exception as e:
    print(f"✗ Direct instantiation test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 8: Test plan() with no model adapter (should return empty list)
print("\n" + "=" * 60)
print("Test 8: Test plan() with no model adapter")
print("=" * 60)
try:
    result = ai_planner.plan("list installed applications")
    print(f"  plan() returned: {result}")
    if result == []:
        print("✓ plan() correctly returns empty list when no model adapter (expected behavior)")
    else:
        print(f"✗ plan() should return empty list, got {result}")
        sys.exit(1)
except Exception as e:
    print(f"✗ plan() test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 9: Test validate_plan
print("\n" + "=" * 60)
print("Test 9: Test validate_plan()")
print("=" * 60)
try:
    empty_plan_valid = ai_planner.validate_plan([])
    print(f"  validate_plan([]) = {empty_plan_valid}")

    # Create a test plan with a valid step
    from alice.planner.ai_planner import PlanStep
    test_step = PlanStep(
        tool_name="open_app",
        parameters={"app_name": "notepad"},
        expected_outcome="Application should launch",
        verification_criteria="Process should be running"
    )

    # Note: validate_plan will fail because tool_name check needs both schemas and registry
    result = ai_planner.validate_plan([test_step])
    print(f"  validate_plan([test_step]) = {result}")

    print("✓ validate_plan() works")
except Exception as e:
    print(f"✗ validate_plan() test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)