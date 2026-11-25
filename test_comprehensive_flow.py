#!/usr/bin/env python3
"""Comprehensive test for the tool execution flow."""
import asyncio
import json
from alice.core.application import AliceApplication
from alice.core.config import Config
from alice.tools.tools import create_default_tools
from alice.planner.planner import TaskPlanner, TaskStep

def test_direct_tool_execution():
    """Test Direct tool execution with different argument formats."""
    print("=" * 60)
    print("TEST: Direct tool execution")
    print("=" * 60)

    registry = create_default_tools()
    tool = registry.get("open_app")

    # Test 1: with 'app' parameter (AI-generated)
    print("\n1. Testing with 'app' parameter (AI format):")
    try:
        result = tool.execute(app="notepad")
        print(f"   SUCCESS: {result.get('status')} - {result.get('message')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 2: with 'app_name' parameter
    print("\n2. Testing with 'app_name' parameter (planner format):")
    try:
        result = tool.execute(app_name="notepad")
        print(f"   SUCCESS: {result.get('status')} - {result.get('message')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 3: with both parameters
    print("\n3. Testing with both 'app' and 'app_name':")
    try:
        result = tool.execute(app="notepad", app_name="calculator")
        print(f"   SUCCESS: {result.get('status')} - {result.get('message')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 4: Test type_text with 'text' parameter
    print("\n4. Testing type_text with 'text' parameter:")
    tool = registry.get("type_text")
    try:
        result = tool.execute(text="Hello from ALICE")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 5: Test type_text with 'message' parameter
    print("\n5. Testing type_text with 'message' parameter:")
    tool = registry.get("type_text")
    try:
        result = tool.execute(message="Hello from ALICE")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 6: Test keyboard_shortcut with 'keys' parameter
    print("\n6. Testing keyboard_shortcut with 'keys' parameter:")
    tool = registry.get("keyboard_shortcut")
    try:
        result = tool.execute(keys="ctrl+c")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 7: Test mouse_move with 'x' and 'y' parameters
    print("\n7. Testing mouse_move with 'x' and 'y' parameters:")
    tool = registry.get("mouse_move")
    try:
        result = tool.execute(x=100, y=200)
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 8: Test mouse_click with parameters
    print("\n8. Testing mouse_click with parameters:")
    tool = registry.get("mouse_click")
    try:
        result = tool.execute(button="left", clicks=1)
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 9: Test select_text with 'method' parameter
    print("\n9. Testing select_text with 'method' parameter:")
    tool = registry.get("select_text")
    try:
        result = tool.execute(method="all")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 10: Test copy_paste with 'action' parameter
    print("\n10. Testing copy_paste with 'action' parameter:")
    tool = registry.get("copy_paste")
    try:
        result = tool.execute(action="copy")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 11: Test set_clipboard with 'content' parameter
    print("\n11. Testing set_clipboard with 'content' parameter:")
    tool = registry.get("set_clipboard")
    try:
        result = tool.execute(content="test data")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 12: Test save_file with parameters
    print("\n12. Testing save_file with parameters:")
    tool = registry.get("save_file")
    try:
        result = tool.execute(path=r"C:\Users\Khushwant\Desktop\test_alice_file.txt", content="Test content from ALICE")
        print(f"   SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   FAILED: {e}")


def test_task_step_execution():
    """Test TaskStep execution."""
    print("\n" + "=" * 60)
    print("TEST: TaskStep execution")
    print("=" * 60)

    registry = create_default_tools()

    # Test 1: TaskStep with 'app_name' (planner format)
    print("\n1. TaskStep with 'app_name' parameter:")
    step = TaskStep(1, "Open notepad", "open_app", {"app_name": "notepad"})
    try:
        step.execute(registry)
        print(f"   SUCCESS: {step.result.get('status') if step.result else step.error}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 2: TaskStep with 'app' parameter (AI format)
    print("\n2. TaskStep with 'app' parameter:")
    step = TaskStep(2, "Open calculator", "open_app", {"app": "calculator"})
    try:
        step.execute(registry)
        print(f"   SUCCESS: {step.result.get('status') if step.result else step.error}")
    except TypeError as e:
        print(f"   FAILED: {e}")

    # Test 3: TaskStep with type_text using 'text'
    print("\n3. TaskStep with type_text using 'text' parameter:")
    step = TaskStep(3, "Type text", "type_text", {"text": "Hello"})
    try:
        step.execute(registry)
        print(f"   SUCCESS: {step.result.get('status') if step.result else step.error}")
    except TypeError as e:
        print(f"   FAILED: {e}")


def test_normalization():
    """Test argument normalization."""
    print("\n" + "=" * 60)
    print("TEST: Argument normalization")
    print("=" * 60)

    config = Config.load()
    app = AliceApplication(config)

    # Test 1: Normalize 'app' to 'app_name'
    print("\n1. Normalize {'app': 'notepad'} to {'app_name': 'notepad'}:")
    normalized = app._normalize_tool_arguments("open_app", {"app": "notepad"})
    print(f"   Result: {normalized}")
    assert normalized == {"app_name": "notepad"}, f"Expected app_name, got {normalized}"

    # Test 2: Normalize 'app_name' stays same
    print("\n2. Normalize {'app_name': 'notepad'} stays same:")
    normalized = app._normalize_tool_arguments("open_app", {"app_name": "notepad"})
    print(f"   Result: {normalized}")
    assert normalized == {"app_name": "notepad"}, f"Expected app_name, got {normalized}"

    # Test 3: Close app normalization
    print("\n3. Normalize close_app {'app': 'notepad'} to {'app_name': 'notepad'}:")
    normalized = app._normalize_tool_arguments("close_app", {"app": "notepad"})
    print(f"   Result: {normalized}")

    # Test 4: Focus app normalization
    print("\n4. Normalize focus_app {'app': 'notepad'} to {'app_name': 'notepad'}:")
    normalized = app._normalize_tool_arguments("focus_app", {"app": "notepad"})
    print(f"   Result: {normalized}")

    # Test 5: Normalize type_text arguments
    print("\n5. Normalize type_text {'text': 'hello'}:")
    # Note: normalization only converts 'app' to 'app_name', so text stays as text
    normalized = app._normalize_tool_arguments("type_text", {"text": "hello"})
    print(f"   Result: {normalized}")

    # Test 6: Normalize keyboard_shortcut arguments
    print("\n6. Normalize keyboard_shortcut {'keys': 'ctrl+c'}:")
    normalized = app._normalize_tool_arguments("keyboard_shortcut", {"keys": "ctrl+c"})
    print(f"   Result: {normalized}")

    # Test 7: Normalize save_file arguments
    print("\n7. Normalize save_file {'path': '/tmp/test.txt', 'content': 'data'}:")
    normalized = app._normalize_tool_arguments("save_file", {"path": "/tmp/test.txt", "content": "data"})
    print(f"   Result: {normalized}")


def test_type_text_signature():
    """Test TypeTextTool signature."""
    print("\n" + "=" * 60)
    print("TEST: TypeTextTool signature")
    print("=" * 60)

    registry = create_default_tools()
    tool = registry.get("type_text")

    print(f"\nTypeTextTool.execute signature check:")
    import inspect
    sig = inspect.signature(tool.execute)
    print(f"   Signature: {sig}")

    # Test with keyword argument
    try:
        result = tool.execute(text="Hello")
        print(f"   Keyword arg SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   Keyword arg FAILED: {e}")

    # Test with 'message' alias
    try:
        result = tool.execute(message="Hello")
        print(f"   Message alias SUCCESS: {result.get('status')}")
    except TypeError as e:
        print(f"   Message alias FAILED: {e}")


def test_all_apps():
    """Test all required applications: Notepad, Calculator, Chrome, File Explorer, VS Code."""
    print("\n" + "=" * 60)
    print("TEST: Opening all required applications")
    print("=" * 60)

    registry = create_default_tools()
    apps = ["notepad", "calculator", "chrome", "explorer", "code"]

    for app_name in apps:
        print(f"\nTesting open_app('{app_name}'):")
        tool = registry.get("open_app")
        try:
            result = tool.execute(app=app_name)
            if result.get("status") == "success":
                print(f"   SUCCESS: {result.get('message')}")
            else:
                print(f"   Result: {result.get('message', result.get('error', 'Unknown error'))}")
        except TypeError as e:
            print(f"   FAILED: {e}")


def main():
    test_direct_tool_execution()
    test_task_step_execution()
    test_normalization()
    test_type_text_signature()
    test_all_apps()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()