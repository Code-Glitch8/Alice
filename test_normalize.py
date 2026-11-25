#!/usr/bin/env python3
"""Test argument normalization."""
from alice.core.application import AliceApplication
from alice.core.config import Config

def test_normalize():
    config = Config.load()
    app = AliceApplication(config)

    # Test normalization for open_app
    print("Testing _normalize_tool_arguments...")

    # AI sends: {"app": "notepad"}
    arguments = {"app": "notepad"}
    normalized = app._normalize_tool_arguments("open_app", arguments)
    print(f"Input: {arguments}")
    print(f"Normalized: {normalized}")
    print()

    # Test with app_name (direct call)
    arguments = {"app_name": "notepad"}
    normalized = app._normalize_tool_arguments("open_app", arguments)
    print(f"Input: {arguments}")
    print(f"Normalized: {normalized}")
    print()

    # Now let's test the actual execute flow
    from alice.tools.tools import create_default_tools
    tooling = create_default_tools()
    tool = tooling.get("open_app")

    print("Testing tool.execute() with normalized arguments...")
    result = tool.execute(**normalized)
    print(f"Result: {result}")

    # Test that both 'app' and 'app_name' work directly with execute()
    print("\n\nTesting direct execute with 'app' parameter (no normalization needed):")
    result = tool.execute(app="calculator")
    print(f"Result: {result}")

    print("\n\nTesting direct execute with 'app_name' parameter:")
    result = tool.execute(app_name="notepad")
    print(f"Result: {result}")


if __name__ == "__main__":
    test_normalize()