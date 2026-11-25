#!/usr/bin/env python3
"""Test has_tool_calls parsing flow for native LM Studio tool calling."""
import json
import unittest
from unittest.mock import MagicMock, patch

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter


class TestHasToolCallsParsing(unittest.TestCase):
    """Test the has_tool_calls format parsing in _parse_ai_response."""

    def setUp(self):
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            self.app = AliceApplication(mock_config)

    def test_parse_has_tool_calls_format_with_json_string_args(self):
        """Test parsing response with has_tool_calls flag and JSON string arguments."""
        # This is what _parse_response in lmstudio_adapter.py returns
        response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}'
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)
        self.assertEqual(result['content'], None)
        self.assertEqual(len(result['tool_calls']), 1)

        tc = result['tool_calls'][0]
        self.assertEqual(tc['id'], 'call_123')
        self.assertEqual(tc['type'], 'function')
        self.assertEqual(tc['function']['name'], 'open_app')
        self.assertIsInstance(tc['function']['arguments'], str)
        self.assertEqual(tc['function']['arguments'], '{"app_name": "notepad"}')

    def test_parse_has_tool_calls_format_with_none_content(self):
        """Test parsing response with has_tool_calls flag and None content."""
        response = '{"content": null, "tool_calls": [{"id": "call_456", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"chrome\\"}"}}], "has_tool_calls": true}'
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)
        self.assertIn('content', result)

    def test_parse_has_tool_calls_format_with_text_content(self):
        """Test parsing response with has_tool_calls flag and text content."""
        response = '{"content": "Let me open Chrome for you.", "tool_calls": [{"id": "call_789", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"chrome\\"}"}}], "has_tool_calls": true}'
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertEqual(result['content'], 'Let me open Chrome for you.')
        self.assertEqual(len(result['tool_calls']), 1)

    def test_parse_markdown_fenced_has_tool_calls(self):
        """Test parsing markdown-fenced JSON with has_tool_calls flag."""
        response = '''```json
{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\\"app_name\\": \\"notepad\\"}"}}], "has_tool_calls": true}
```'''
        result = self.app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)
        self.assertEqual(result['content'], None)


if __name__ == "__main__":
    unittest.main()