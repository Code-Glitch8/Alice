#!/usr/bin/env python3
"""Integration test for chat_with_tools with native LM Studio tool calling."""
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.runtime_manager import RuntimeManager
from alice.core.config import Config


class TestChatWithToolsIntegration(unittest.TestCase):
    """Test the complete chat_with_tools flow."""

    def setUp(self):
        self.config = Config()
        self.config.ai.base_url = "http://127.0.0.1:1234"
        self.config.ai.auto_start_server = False
        self.config.automation.auto_confirm_category_a = True
        self.config.automation.require_confirm_category_b = False
        self.config.automation.restricted_category_c = False
        self.config.automation.max_tool_calls = 5

    def test_chat_with_tools_parses_has_tool_calls_response(self):
        """Test that chat_with_tools correctly parses has_tool_calls format."""
        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(self.config)
            app.ai_adapter = LMStudioAdapter(self.config)

        # Mock the adapter to return tool call response (simulating LM Studio)
        async def mock_chat(messages, **kwargs):
            # Check that tools were passed
            if 'tools' in kwargs:
                tool_names = [t.get('function', {}).get('name') for t in kwargs['tools']]
                assert 'open_app' in tool_names, "open_app tool should be in the tools list"
            return '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'

        app.runtime.chat = mock_chat

        async def run_test():
            # Mock _execute_tool_calls since we don't want actual tool execution
            async def mock_execute_tool_calls(tool_calls, history, content):
                return f"Executed {len(tool_calls)} tool calls"

            app._execute_tool_calls = mock_execute_tool_calls

            result = await app.chat_with_tools([{"role": "user", "content": "Open notepad"}])
            return result

        result = asyncio.run(run_test())
        assert "Executed 1 tool calls" in result


if __name__ == "__main__":
    unittest.main()