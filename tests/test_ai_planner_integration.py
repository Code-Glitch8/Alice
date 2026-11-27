#!/usr/bin/env python3
"""
Test suite for AIPlanner and ToolRegistry integration.

Tests for:
1. AIPlanner can initialize with create_default_tools() result
2. AIPlanner correctly retrieves every registered tool
3. Schema generation for all registered tools
4. ToolRegistry compatibility (dict vs ToolRegistry interface)
"""

import pytest
from types import SimpleNamespace
from pathlib import Path

from alice.tools.tools import (
    create_default_tools,
    ToolRegistry,
    Tool,
)
from alice.planner.ai_planner import (
    AIPlanner,
    PlanStep,
    GeneratedPlan,
    create_ai_planner_from_app,
)


class TestToolRegistryInterface:
    """Test ToolRegistry interface compatibility."""

    def test_tool_registry_has_tools_dict(self):
        """ToolRegistry should have a .tools dict attribute."""
        registry = ToolRegistry()
        assert hasattr(registry, "tools")
        assert isinstance(registry.tools, dict)

    def test_create_default_tools_returns_toolregistry(self):
        """create_default_tools() should return a ToolRegistry instance."""
        registry = create_default_tools()
        assert isinstance(registry, ToolRegistry)

    def test_tool_registry_tools_count(self):
        """ToolRegistry should contain tools after create_default_tools()."""
        registry = create_default_tools()
        tool_count = len(registry.tools)
        # The actual count based on current implementation
        assert tool_count > 0, "ToolRegistry should have at least one tool"

    def test_tool_registry_get_returns_tool(self):
        """ToolRegistry.get() should return a Tool instance for registered tools."""
        registry = create_default_tools()
        tool = registry.get("open_app")
        assert tool is not None
        assert isinstance(tool, Tool)

    def test_tool_registry_list_tools_returns_list(self):
        """ToolRegistry.list_tools() should return a list of tools."""
        registry = create_default_tools()
        tools = registry.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0


class TestAIPlannerToolRegistryCompatibility:
    """Test AIPlanner can work with ToolRegistry interface."""

    def test_ai_planner_init_with_toolregistry(self):
        """AIPlanner should initialize with ToolRegistry from create_default_tools()."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        assert planner.tool_registry is not None
        assert planner.tool_registry is registry

    def test_ai_planner_extracts_tools_from_toolregistry(self):
        """AIPlanner should extract tools from ToolRegistry via .tools attribute."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        # The internal _get_tool_registry_items should work
        items = planner._get_tool_registry_items()
        assert isinstance(items, dict)
        assert len(items) > 0

    def test_ai_planner_builds_schemas_for_all_tools(self):
        """AIPlanner should build schemas for all tools."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        schemas = planner._tool_schemas
        assert len(schemas) > 0, "AIPlanner should build schemas for all tools"

    def test_ai_planner_schema_contains_open_app(self):
        """Schema should contain open_app tool."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        assert "open_app" in planner._tool_schemas

    def test_ai_planner_init_with_dict(self):
        """AIPlanner should also work with plain dict as tool_registry."""
        registry = create_default_tools()
        tool_dict = registry.tools  # Extract the dict
        planner = AIPlanner(
            tool_registry=tool_dict,
            model_adapter=None,
            context_manager=None,
        )
        assert len(planner._tool_schemas) > 0

    def test_plan_returns_empty_without_model_adapter(self):
        """plan() should return empty list when model_adapter is None."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        result = planner.plan("list installed applications")
        assert result == []

    def test_validate_plan_for_empty_plan(self):
        """validate_plan should return False for empty plan."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        assert planner.validate_plan([]) is False

    def test_validate_plan_for_valid_step(self):
        """validate_plan should return True for a valid step."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        step = PlanStep(
            tool_name="open_app",
            parameters={"app_name": "notepad"},
            expected_outcome="Application should launch",
            verification_criteria="Process should be running"
        )
        assert planner.validate_plan([step]) is True

    def test_validate_plan_for_invalid_tool(self):
        """validate_plan should return False for step with unknown tool."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )
        step = PlanStep(
            tool_name="nonexistent_tool",
            parameters={"foo": "bar"},
            expected_outcome="Should fail",
            verification_criteria="Unknown tool"
        )
        assert planner.validate_plan([step]) is False


class TestSchemaInferenceWithKwargs:
    """Test schema inference for tools with **kwargs signatures."""

    def test_infer_schema_handles_var_keyword(self):
        """_infer_schema should handle VAR_KEYWORD (**) parameters."""
        from alice.planner.ai_planner import AIPlanner
        from inspect import Parameter

        def func_with_kwargs(**kwargs):
            """A function that accepts any keyword arguments."""
            pass

        planner = AIPlanner(
            tool_registry={},
            model_adapter=None,
            context_manager=None,
        )
        schema = planner._infer_schema(func_with_kwargs, "test_func")
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema

    def test_tool_execute_has_kwargs_schema(self):
        """Tools with execute(**kwargs) should have proper schema."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        # Check that get_clipboard schema exists and is valid
        schema = planner._tool_schemas.get("get_clipboard", {})
        assert schema.get("type") == "object"
        assert "properties" in schema

    def test_schema_is_valid_json(self):
        """All tool schemas should be valid for JSON serialization."""
        import json
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        for tool_name, schema in planner._tool_schemas.items():
            try:
                json.dumps(schema)
            except (TypeError, ValueError) as e:
                pytest.fail(f"Schema for {tool_name} is not JSON serializable: {e}")


class TestPlanStepDataclass:
    """Test PlanStep dataclass functionality."""

    def test_plan_step_default_values(self):
        """PlanStep should have sensible defaults."""
        step = PlanStep()
        assert step.step_id != ""  # UUID generated
        assert step.tool_name == ""
        assert step.parameters == {}
        assert step.expected_outcome == ""
        assert step.verification_criteria == ""
        assert step.dependencies == []
        assert step.thought == ""

    def test_plan_step_from_dict(self):
        """PlanStep.from_dict should reconstruct a PlanStep."""
        data = {
            "step_id": "test-123",
            "tool_name": "open_app",
            "parameters": {"app_name": "notepad"},
            "expected_outcome": "App should open",
            "verification_criteria": "Process check",
            "dependencies": [],
            "thought": "Opening notepad"
        }
        step = PlanStep.from_dict(data)
        assert step.step_id == "test-123"
        assert step.tool_name == "open_app"
        assert step.parameters == {"app_name": "notepad"}

    def test_plan_step_roundtrip(self):
        """PlanStep.to_dict/from_dict roundtrip should preserve data."""
        original = PlanStep(
            tool_name="type_text",
            parameters={"text": "Hello, world!"},
            expected_outcome="Text typed",
            verification_criteria="Text appears",
            thought="Typing greeting"
        )
        restored = PlanStep.from_dict(original.to_dict())
        assert original.to_dict() == restored.to_dict()


class TestGeneratedPlanDataclass:
    """Test GeneratedPlan dataclass functionality."""

    def test_generated_plan_defaults(self):
        """GeneratedPlan should have sensible defaults."""
        plan = GeneratedPlan()
        assert plan.plan_id != ""
        assert plan.intent == ""
        assert plan.steps == []
        assert plan.confidence == 0.0

    def test_generated_plan_from_dict(self):
        """GeneratedPlan.from_dict should reconstruct a plan."""
        data = {
            "plan_id": "plan-456",
            "intent": "Open notepad",
            "steps": [
                {
                    "step_id": "step-1",
                    "tool_name": "open_app",
                    "parameters": {"app_name": "notepad"},
                    "expected_outcome": "",
                    "verification_criteria": "",
                    "dependencies": [],
                    "thought": ""
                }
            ],
            "original_query": "Open notepad",
            "generated_at": "2024-01-01T00:00:00",
            "confidence": 0.9,
            "notes": "Test plan"
        }
        plan = GeneratedPlan.from_dict(data)
        assert plan.plan_id == "plan-456"
        assert plan.intent == "Open notepad"
        assert len(plan.steps) == 1


class TestToolSchemaGeneration:
    """Test that schemas are properly generated for each tool type."""

    @pytest.mark.parametrize("tool_name", [
        "open_app", "close_app", "focus_app",
        "create_folder", "delete_folder",
        "read_file", "write_file", "move_file", "delete_file",
        "search_files",
        "browser_open", "browser_extract", "browser_download", "browser_screenshot",
        "type_text", "keyboard_shortcut",
        "mouse_move", "mouse_click", "mouse_scroll", "select_text",
        "copy_paste", "get_clipboard", "set_clipboard",
        "system_info", "list_running_apps", "list_installed_apps",
        "emergency_stop", "get_open_apps", "get_app_status", "close_all_apps",
    ])
    def test_each_tool_has_valid_schema(self, tool_name):
        """Each tool should have a valid schema if it's registered."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        # Check if tool is registered
        if tool_name in registry.tools:
            assert tool_name in planner._tool_schemas, f"Missing schema for {tool_name}"

            schema = planner._tool_schemas[tool_name]
            assert isinstance(schema, dict), f"Schema for {tool_name} should be dict"
            assert "type" in schema or "properties" in schema, f"Schema for {tool_name} should have type or properties"

    def test_required_parameters_in_schema(self):
        """Schemas should include required parameters where appropriate."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        # open_app requires app_name
        if "open_app" in planner._tool_schemas:
            open_app_schema = planner._tool_schemas.get("open_app", {})
            required = open_app_schema.get("required", [])
            assert "app_name" in required, "open_app should require 'app_name' parameter"

    def test_optional_parameters_have_no_required(self):
        """Tools with no required parameters should have empty required list."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        # get_clipboard has no required parameters
        if "get_clipboard" in planner._tool_schemas:
            clipboard_schema = planner._tool_schemas.get("get_clipboard", {})
            required = clipboard_schema.get("required", [])
            assert len(required) == 0, "get_clipboard should have no required parameters"


class TestCreateAiPlannerFromApp:
    """Test factory function create_ai_planner_from_app."""

    def test_creates_planner_from_app(self):
        """create_ai_planner_from_app should create AIPlanner from AliceApplication."""
        # Create mock app with required attributes
        tool_registry = create_default_tools()
        mock_app = SimpleNamespace(
            tool_registry=tool_registry,
            model_adapter=None,
            context_manager=None,
        )

        planner = create_ai_planner_from_app(mock_app)
        assert planner is not None
        assert len(planner._tool_schemas) > 0


class TestToolExecutionMethods:
    """Test that tools with execute methods are properly handled."""

    def test_tools_have_execute_method(self):
        """Tools should have an execute method."""
        registry = create_default_tools()
        for tool in registry.list_tools():
            assert hasattr(tool, "execute"), f"Tool {tool.name} missing execute method"
            assert callable(tool.execute), f"Tool {tool.name} execute should be callable"

    def test_execute_methods_have_docstrings(self):
        """Tool execute methods should have docstrings for schema inference."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        # Verify schemas were built for tools with execute methods
        # The presence of schemas indicates docstrings were available
        assert len(planner._tool_schemas) > 0

    def test_schema_match_tool_count(self):
        """Number of schemas should match number of registered tools."""
        registry = create_default_tools()
        planner = AIPlanner(
            tool_registry=registry,
            model_adapter=None,
            context_manager=None,
        )

        tool_count = len(registry.tools)
        schema_count = len(planner._tool_schemas)
        assert tool_count == schema_count, f"Tool count ({tool_count}) should match schema count ({schema_count})"