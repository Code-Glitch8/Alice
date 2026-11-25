#!/usr/bin/env python3
"""Test the tool calling integration."""
import asyncio
import json
from unittest.mock import MagicMock, patch

from alice.core.application import AliceApplication
from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.runtime_manager import RuntimeManager
from alice.core.config import Config


def test_chat_with_tools_native():
    """Test chat_with_tools with native tool calling."""
    # Create config
    config = Config()
    config.ai.base_url = "http://127.0.0.1:1234"
    config.ai.auto_start_server = False
    config.automation.auto_confirm_category_a = True
    config.automation.require_confirm_category_b = False
    config.automation.restricted_category_c = False
    config.automation.max_tool_calls = 5

    # Create adapter with mocked _request
    with patch.object(LMStudioAdapter, '_request', return_value={}):
        adapter = LMStudioAdapter(config)
        adapter.model_loaded = True
        adapter.current_model = "qwen-test"

        manager = RuntimeManager(adapter, config)

        # Mock the _parse_response to return tool calls
        def mock_request(method, path, payload=None, **kwargs):
            if path == "/api/v1/models":
                return {
                    "models": [{
                        "type": "llm",
                        "key": "qwen/qwen3.5-4b-q4_k_m",
                        "loaded_instances": [{"id": "test-instance"}],
                        "capabilities": {"trained_for_tool_use": True}
                    }]
                }
            elif path == "/api/v1/models/load":
                return {"status": "loaded", "instance_id": "test-instance"}
            elif path == "/v1/chat/completions":
                # Return a response with tool calls
                return {
                    "choices": [{
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "open_app",
                                    "arguments": '{"app_name": "notepad"}'
                                }
                            }]
                        }
                    }]
                }
            return {}

        adapter._request = mock_request

        # Create app
        app = AliceApplication(config)
        app.ai_adapter = adapter
        app.runtime = manager
        app.tool_dispatcher.call_count = 0

        # Test _parse_ai_response directly
        response = '{"content": null, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "open_app", "arguments": "{\"app_name\": \"notepad\"}"}}], "has_tool_calls": true}'
        parsed = app._parse_ai_response(response)
        print("Parsed response:", parsed)
        print("Has tool_calls:", "tool_calls" in parsed if parsed else False)

        if parsed and "tool_calls" in parsed:
            print("Tool calls:", parsed["tool_calls"])
            tc = parsed["tool_calls"][0]
            args = tc["function"]["arguments"]
            print("Arguments type:", type(args))
            print("Arguments:", args)


if __name__ == "__main__":
    test_chat_with_tools_native()
    print("\nTest complete!")