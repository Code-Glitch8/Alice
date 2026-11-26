#!/usr/bin/env python3
"""Integration tests for the iterative ALICE tool-call conversation loop."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.core.config import Config


class TestChatWithToolsIntegration(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.ai.base_url = "http://127.0.0.1:1234"
        self.config.ai.auto_start_server = False
        self.config.automation.auto_confirm_category_a = True
        self.config.automation.require_confirm_category_b = False
        self.config.automation.restricted_category_c = False

    def test_chat_with_tools_executes_tool_and_then_returns_final_answer(self):
        with patch.object(LMStudioAdapter, "_request", return_value={}):
            app = AliceApplication(self.config)

        responses = [
            json.dumps({
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "open_app", "arguments": {"app_name": "notepad"}}
                }],
                "has_tool_calls": True
            }),
            "Notepad is open."
        ]
        sent_messages = []

        async def mock_chat(messages, **kwargs):
            sent_messages.append([dict(message) for message in messages])
            return responses.pop(0)

        app.runtime.chat = mock_chat
        app.initialized = True
        app.tool_dispatcher.execute_async = AsyncMock(
            return_value={"status": "success", "message": "Opened Notepad"}
        )

        result = asyncio.run(app.chat_with_tools([
            {"role": "user", "content": "Open notepad"}
        ]))

        self.assertEqual(result, "Notepad is open.")
        app.tool_dispatcher.execute_async.assert_awaited_once_with(
            "open_app", {"app_name": "notepad"}
        )
        self.assertEqual(len(sent_messages), 2)
        for messages in sent_messages:
            system_messages = [message for message in messages if message["role"] == "system"]
            self.assertEqual(len(system_messages), 1)
            self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(sent_messages[1][-1]["role"], "tool")
        self.assertEqual(sent_messages[1][-1]["tool_call_id"], "call_123")


if __name__ == "__main__":
    unittest.main()
