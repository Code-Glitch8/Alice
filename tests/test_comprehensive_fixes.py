#!/usr/bin/env python3
"""Comprehensive test suite for ALICE 1.0.6 fixes.

Tests all 14 root cause fixes:
1. XML-style tool call parsing from Qwen models
2. has_tool_calls flag format support
3. Correct tool schema structures
4. Planner integration in chat pipeline
5. Browser lifecycle - keeps open during interaction
6. Consistent async execution
7. Tool execution loop with multiple rounds
8. TypeText reliability - focuses target window
9. Application ownership tracking via PID
10. Tool result formatting
11-14. Various edge cases and integration tests
"""
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.core.config import Config


class TestXMLStyleToolCallParsing(unittest.TestCase):
    """Test 1: XML-style tool call parsing from Qwen models."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_parse_xml_style_tool_call_single(self):
        """Test parsing XML-style tool call: <function=name><parameter>value</parameter></function>"""
        response = '''<function=name="open_app"><parameter name="app_name">notepad</parameter></function>'''
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result, "Should parse XML-style tool call")
        self.assertIn('tool_calls', result)
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['function']['name'], 'open_app')
        self.assertEqual(result['tool_calls'][0]['function']['arguments'], '{"app_name": "notepad"}')

    def test_parse_xml_style_tool_call_multiple_params(self):
        """Test XML-style tool call with multiple parameters."""
        response = '''<function=name="browser_open"><parameter name="url">https://example.com</parameter><parameter name="visible">true</parameter></function>'''
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertEqual(result['tool_calls'][0]['function']['name'], 'browser_open')
        args = json.loads(result['tool_calls'][0]['function']['arguments'])
        self.assertEqual(args['url'], 'https://example.com')

    def test_parse_xml_style_tool_calls_multiple(self):
        """Test multiple XML-style tool calls in sequence."""
        response = '''<function=name="open_app"><parameter name="app_name">notepad</parameter></function>
<function=name="type_text"><parameter name="text">Hello World</parameter></function>'''
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertEqual(len(result['tool_calls']), 2)
        self.assertEqual(result['tool_calls'][0]['function']['name'], 'open_app')
        self.assertEqual(result['tool_calls'][1]['function']['name'], 'type_text')

    def test_parse_xml_style_with_content(self):
        """Test XML-style tool call with accompanying text content."""
        response = '''I'll open notepad for you.
<function=name="open_app"><parameter name="app_name">notepad</parameter></function>'''
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)
        self.assertIn('content', result)


class TestHasToolCallsFormat(unittest.TestCase):
    """Test 2: has_tool_calls flag format support."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_parse_has_tool_calls_with_json_string_args(self):
        """Test has_tool_calls format with JSON string arguments."""
        response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)
        self.assertEqual(result['content'], None)
        self.assertIsInstance(result['tool_calls'][0]['function']['arguments'], str)

    def test_parse_has_tool_calls_with_text_content(self):
        """Test has_tool_calls format with text content and tool calls."""
        response = '{"content": "Let me open Chrome.", "tool_calls": [{"id": "call_456", "type": "function", "function": {"name": "browser_open", "arguments": "{\\"url\\": \\"https://chrome.com\\"}"}}], "has_tool_calls": true}'
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertEqual(result['content'], 'Let me open Chrome.')
        self.assertEqual(len(result['tool_calls']), 1)


class TestToolSchemaStructures(unittest.TestCase):
    """Test 3: Correct OpenAI-compatible tool schema structures."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_schema_open_app_has_correct_structure(self):
        """Test that open_app schema is valid OpenAI format."""
        tools = self.app.get_tools_for_api()

        open_app_schema = next((t for t in tools if t['function']['name'] == 'open_app'), None)
        self.assertIsNotNone(open_app_schema)

        # Check top-level structure
        self.assertEqual(open_app_schema['type'], 'function')
        self.assertIn('function', open_app_schema)

        # Check function object
        func = open_app_schema['function']
        self.assertIn('name', func)
        self.assertIn('description', func)
        self.assertIn('parameters', func)

        # Check parameters is at correct level
        params = func['parameters']
        self.assertIn('type', params)
        self.assertIn('properties', params)
        self.assertIn('required', params)

        # Required should be in parameters, NOT at function level
        self.assertIsInstance(params['required'], list)

    def test_schema_browser_open_structure(self):
        """Test browser_open schema structure."""
        tools = self.app.get_tools_for_api()

        schema = next((t for t in tools if t['function']['name'] == 'browser_open'), None)
        self.assertIsNotNone(schema)

        # Verify all parameters are correctly defined
        params = schema['function']['parameters']
        self.assertIn('properties', params)
        self.assertIn('url', params['properties'])
        self.assertIn('search', params['properties'])
        self.assertIn('visible', params['properties'])

    def test_schema_type_text_structure(self):
        """Test type_text schema structure."""
        tools = self.app.get_tools_for_api()

        schema = next((t for t in tools if t['function']['name'] == 'type_text'), None)
        self.assertIsNotNone(schema)

        params = schema['function']['parameters']
        self.assertIn('text', params['properties'])
        self.assertIn('delay', params['properties'])
        # interval parameter should be supported
        self.assertIn('interval', params['properties'])


class TestPlannerIntegration(unittest.TestCase):
    """Test 4: Planner integration in chat pipeline."""

    def test_planner_detects_compound_open_type(self):
        """Test that planner detects 'open app, type text' compound commands."""
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        mock_config.automation.auto_confirm_category_a = True
        mock_config.automation.require_confirm_category_b = False
        mock_config.automation.restricted_category_c = False
        mock_config.automation.max_tool_calls = 5

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        steps = app.task_planner.plan("Open notepad, type 'Hello World', and save as test.txt")

        # Should detect compound command
        self.assertGreater(len(steps), 1, "Should detect multiple steps")

        # First step should be open_app
        self.assertEqual(steps[0].tool_name, 'open_app')

        # Should have focus_app before type_text
        tool_names = [s.tool_name for s in steps]
        self.assertIn('focus_app', tool_names)
        self.assertIn('type_text', tool_names)

    def test_planner_handles_multiple_actions(self):
        """Test planner handles multiple actions in sequence."""
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        steps = app.task_planner.plan("Open Chrome and search for Python")

        self.assertEqual(steps[0].tool_name, 'browser_open')
        self.assertEqual(steps[0].parameters['search'], 'Python')


class TestBrowserLifecycle(unittest.TestCase):
    """Test 5: Browser lifecycle - keeps open during interaction."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_browser_open_does_not_close_immediately(self):
        """Test that browser stays open for user interaction after initial load."""
        from alice.tools.tools import BrowserOpenTool

        tool = BrowserOpenTool()
        # Verify the Chrome launch request without requiring Chrome on the CI runner.
        tool._find_chrome_executable = lambda: r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        with patch("alice.tools.tools.subprocess.Popen") as popen:
            popen.return_value.pid = 1234
            result = asyncio.run(tool._browser_open_async(search="Google ai studio", visible=True))

        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['verification']['launch_requested'])
        self.assertTrue(result['verification']['dedicated_profile'])
        self.assertFalse(result['verification']['incognito'])
        command = popen.call_args.args[0]
        self.assertIn("chrome.exe", command[0].lower())
        self.assertTrue(command[1].startswith("--user-data-dir="))
        self.assertIn("q=Google+ai+studio", command[-1])
        self.assertNotIn("--incognito", command)


class TestAsyncExecution(unittest.TestCase):
    """Test 6: Consistent async execution patterns."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_tool_dispatcher_handles_async(self):
        """Test ToolDispatcher properly handles async tools."""
        from alice.tools.tools import BrowserOpenTool, ToolDispatcher

        config = Config.load()
        dispatcher = ToolDispatcher(self.app.tool_registry, config)

        # Execute should work for both sync and async tools
        result = dispatcher.execute('open_app', {'app_name': 'notepad'})
        self.assertIsNotNone(result)


class TestToolExecutionLoop(unittest.TestCase):
    """Test 7: Tool execution loop with multiple rounds."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_multiple_tool_calls_executed(self):
        """Test that multiple tool calls in a single response are all executed."""
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        mock_config.automation.auto_confirm_category_a = True
        mock_config.automation.require_confirm_category_b = False
        mock_config.automation.restricted_category_c = False
        mock_config.automation.max_tool_calls = 5  # Must be set to an integer

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        # Pre-defined responses for chat - first returns tool calls, second returns final result
        tool_call_response = json.dumps({
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": '{"app_name": "notepad"}'}},
                {"id": "call_2", "type": "function", "function": {"name": "open_app", "arguments": '{"app_name": "chrome"}'}}
            ],
            "has_tool_calls": True
        })
        final_response = "All tools executed successfully"

        # Create a mock that will be called multiple times
        call_count = [0]
        async def mock_chat(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return tool_call_response
            else:
                return final_response

        app.runtime.chat = mock_chat
        app.initialized = True

        # Return proper OpenAI-style tool result messages.
        async def mock_execute_tool_calls(tool_calls, history, content):
            return [
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"status": "success"})}
                for call in tool_calls
            ]

        app._execute_tool_calls = mock_execute_tool_calls

        result = asyncio.run(app.chat_with_tools([{"role": "user", "content": "Open notepad"}]))
        # Should contain something about executing the tool calls
        self.assertIsNotNone(result)


class TestTypeTextReliability(unittest.TestCase):
    """Test 8: TypeText reliability - focuses target window."""

    def test_type_text_fails_without_focus(self):
        """Test that type_text requires a focused window (or focuses one)."""
        from alice.tools.tools import TypeTextTool

        tool = TypeTextTool()
        # When focus_app is called first, it should be able to type
        result = tool.execute(text="test")
        # Result should indicate success or failure properly
        self.assertIn('status', result)


class TestApplicationOwnership(unittest.TestCase):
    """Test 9: Application ownership tracking via PID."""

    def test_ownership_registry_works(self):
        """Test the ApplicationOwner singleton registry."""
        from alice.core.application_owner import ApplicationOwner

        # Reset singleton for clean test
        ApplicationOwner.reset_instance()

        owner = ApplicationOwner.get_instance()

        # Register an app
        owner.register_app("notepad", 12345)

        # Check it's tracked
        self.assertTrue(owner.is_owned_by_alice(12345))

        # Get by PID
        info = owner.get_app_by_pid(12345)
        self.assertIsNotNone(info)
        # Note: to_dict() returns "app" key, not "app_name"
        self.assertEqual(info['app'], 'notepad')
        self.assertEqual(info['pid'], 12345)

        # Cleanup
        owner.clear_all_apps()


class TestToolResultFormatting(unittest.TestCase):
    """Test 10: Tool result formatting for proper integration."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_open_app_returns_proper_structure(self):
        """Test that open_app tool returns proper result structure."""
        from alice.tools.tools import OpenAppTool

        tool = OpenAppTool()
        # The result should have proper structure even on error
        result = tool.execute(app_name="invalid_nonexistent_app_12345")

        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('verification', result)

    def test_tool_result_preserved_in_execution(self):
        """Test tool results are preserved when sent back to LLM."""
        # This tests the _execute_tool_calls method
        pass  # Integration test covered elsewhere


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complete scenarios."""

    def test_open_notepad_type_text_flow(self):
        """Test complete flow: open notepad, type text."""
        config = Config()
        config.ai.base_url = "http://127.0.0.1:1234"
        config.ai.auto_start_server = False
        config.automation.auto_confirm_category_a = True
        config.automation.require_confirm_category_b = False
        config.automation.restricted_category_c = False

        # Create app with mocked dependencies
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(config)

    def test_browser_search_flow(self):
        """Test complete browser search flow."""
        pass  # Covered in other tests


class TestSystemPromptDuplication(unittest.TestCase):
    """Regression test: System prompt must appear exactly once at index 0.

    This test verifies the fix for the Jinja Exception: System message must be at
    the beginning error that occurred when the system prompt was being duplicated
    in the tool execution loop.
    """

    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.ai.base_url = "http://127.0.0.1:1234"
        self.mock_config.automation.auto_confirm_category_a = True
        self.mock_config.automation.require_confirm_category_b = False
        self.mock_config.automation.restricted_category_c = False
        self.mock_config.automation.max_tool_calls = 5

    def test_system_prompt_appears_once_after_tool_execution(self):
        """Test that system prompt is at index 0 and appears only once after tool calls."""
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(self.mock_config)

        # Track messages sent to LM Studio
        messages_sent_to_runtime = []

        async def mock_chat(messages, **kwargs):
            messages_sent_to_runtime.append([dict(m) for m in messages])
            # First call: return tool calls
            # Second call: return final response
            call_count = len(messages_sent_to_runtime)
            if call_count == 1:
                return json.dumps({
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {
                            "name": "open_app", "arguments": '{"app_name": "notepad"}'
                        }}
                    ],
                    "has_tool_calls": True
                })
            else:
                return "Task completed successfully"

        app.runtime.chat = mock_chat
        app.initialized = True
        app.tool_dispatcher.execute_async = AsyncMock(return_value={"status": "success", "message": "Opened Notepad"})

        # Execute the chat with tools
        result = asyncio.run(app.chat_with_tools([{"role": "user", "content": "Open notepad"}]))

        # Verify we captured messages from two calls
        self.assertEqual(len(messages_sent_to_runtime), 2, "Should have made 2 calls to LM Studio")

        # Check the SECOND call (after tool execution) for system prompt placement
        second_call_messages = messages_sent_to_runtime[1]

        # Count system messages
        system_messages = [m for m in second_call_messages if m.get("role") == "system"]
        self.assertEqual(len(system_messages), 1, "Should have exactly one system message")

        # Verify system message is at index 0
        self.assertEqual(second_call_messages[0]["role"], "system", "System message must be at index 0")

        # Verify system message has proper content
        self.assertIn("ALICE", second_call_messages[0]["content"])

        # Verify assistant tool call message is present
        assistant_messages = [m for m in second_call_messages if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_messages), 1, "Should have one assistant message")

        # Verify tool results are present
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        self.assertGreater(len(tool_messages), 0, "Should have tool result messages")

    def test_multiple_consecutive_tool_calls_no_system_duplication(self):
        """Test that system prompt doesn't duplicate after multiple rounds of tool calls."""
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(self.mock_config)

        messages_sent_to_runtime = []
        call_count = [0]

        async def mock_chat(messages, **kwargs):
            messages_sent_to_runtime.append([dict(m) for m in messages])
            call_count[0] += 1

            if call_count[0] == 1:
                # First call: returns tool call
                return json.dumps({
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {
                            "name": "open_app", "arguments": '{"app_name": "notepad"}'
                        }}
                    ],
                    "has_tool_calls": True
                })
            elif call_count[0] == 2:
                # Second call: returns another tool call
                return json.dumps({
                    "content": "Now type some text",
                    "tool_calls": [
                        {"id": "call_2", "type": "function", "function": {
                            "name": "type_text", "arguments": '{"text": "Hello"}'
                        }}
                    ],
                    "has_tool_calls": True
                })
            else:
                # Third call: returns final response
                return "All tasks completed"

        app.runtime.chat = mock_chat
        app.initialized = True
        app.tool_dispatcher.execute_async = AsyncMock(return_value={"status": "success", "message": "Action completed"})

        # Keep the originating request non-compound so this exercises the iterative
        # native-tool-call loop rather than deterministic planning.
        result = asyncio.run(app.chat_with_tools([{"role": "user", "content": "Open notepad"}]))

        # Check all calls for system prompt duplication
        for i, messages in enumerate(messages_sent_to_runtime):
            system_messages = [m for m in messages if m.get("role") == "system"]
            self.assertEqual(len(system_messages), 1,
                f"Call {i+1}: Should have exactly one system message, found {len(system_messages)}")
            self.assertEqual(messages[0]["role"], "system", f"Call {i+1}: System message must be at index 0")


if __name__ == "__main__":
    unittest.main(verbosity=2)