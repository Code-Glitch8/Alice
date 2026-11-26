"""Tests for explicit confirmation of protected Category B actions."""
import asyncio
from unittest.mock import AsyncMock, patch

from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.core.application import AliceApplication
from alice.core.config import Config
from alice.tools.tools import Tool


def make_app():
    config = Config()
    config.ai.base_url = "http://127.0.0.1:1234"
    config.ai.auto_start_server = False
    config.automation.auto_confirm_category_a = True
    config.automation.require_confirm_category_b = True
    config.automation.restricted_category_c = True
    with patch.object(LMStudioAdapter, "_request", return_value={}):
        app = AliceApplication(config)
    app.initialized = True
    return app


def test_cli_confirmation_callback_approves_only_explicit_yes():
    from alice.cli import _confirm_category_b_action

    with patch("alice.cli.asyncio.to_thread", new=AsyncMock(return_value="y")):
        approved = asyncio.run(_confirm_category_b_action("type_text", "Write text in Notepad"))
    assert approved is True

    with patch("alice.cli.asyncio.to_thread", new=AsyncMock(return_value="no")):
        declined = asyncio.run(_confirm_category_b_action("type_text", "Write text in Notepad"))
    assert declined is False


def test_planned_notepad_write_runs_after_category_b_approval():
    app = make_app()
    app.permission_confirmation_callback = AsyncMock(return_value=True)
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Step completed"}
    )
    history = [{
        "role": "user",
        "content": "open notepad and write my favourite color",
    }]

    result = asyncio.run(app._execute_planned_tasks(
        history,
        history[0]["content"],
        [],
    ))

    called_tools = [call.args[0] for call in app.tool_dispatcher.execute_async.await_args_list]
    assert called_tools == ["open_app", "focus_app", "type_text"]
    app.permission_confirmation_callback.assert_awaited_once_with(
        "type_text", "Write text in notepad"
    )
    assert "Completed 3 of 3" in result


def test_declined_category_b_confirmation_prevents_text_entry():
    app = make_app()
    app.permission_confirmation_callback = AsyncMock(return_value=False)
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Step completed"}
    )
    history = [{
        "role": "user",
        "content": "open notepad and write my favourite color",
    }]

    result = asyncio.run(app._execute_planned_tasks(
        history,
        history[0]["content"],
        [],
    ))

    called_tools = [call.args[0] for call in app.tool_dispatcher.execute_async.await_args_list]
    assert called_tools == ["open_app", "focus_app"]
    assert "Category B action was not approved" in result


def test_model_tool_call_also_requests_category_b_approval():
    app = make_app()
    app.permission_confirmation_callback = AsyncMock(return_value=True)
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Text pasted"}
    )
    tool_calls = [{
        "id": "type_1",
        "type": "function",
        "function": {
            "name": "type_text",
            "arguments": '{"text":"A short test note","target_window":"notepad"}',
        },
    }]

    results = asyncio.run(app._execute_tool_calls(tool_calls, [], ""))

    app.permission_confirmation_callback.assert_awaited_once_with(
        "type_text", "Call type_text"
    )
    app.tool_dispatcher.execute_async.assert_awaited_once_with(
        "type_text", {"text": "A short test note", "target_window": "notepad"}
    )
    assert results[0]["tool_call_id"] == "type_1"



def test_one_shot_intent_requests_category_b_approval():
    app = make_app()
    app.permission_confirmation_callback = AsyncMock(return_value=True)
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Closed ALICE Chrome"}
    )

    result = asyncio.run(app.execute_intent("close Chrome"))

    app.permission_confirmation_callback.assert_awaited_once_with(
        "close_app", "Close chrome"
    )
    app.tool_dispatcher.execute_async.assert_awaited_once_with(
        "close_app", {"app_name": "chrome"}
    )
    assert result["steps"][0]["verified"] is True



def test_category_c_remains_blocked_even_if_callback_would_approve():
    class CategoryCTool(Tool):
        def __init__(self):
            super().__init__("restricted_test", "restricted test", required_permission="C")

        def execute(self, **_kwargs):
            return {"status": "success"}

    app = make_app()
    app.permission_confirmation_callback = AsyncMock(return_value=True)
    permitted = asyncio.run(app._is_action_permitted(CategoryCTool(), "restricted action"))

    assert permitted is False
    app.permission_confirmation_callback.assert_not_awaited()
