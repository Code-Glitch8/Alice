"""Regression tests for ALICE's command planning and execution pipeline."""
import asyncio
import json
import threading
from unittest.mock import AsyncMock, patch

from alice.ai.lmstudio_adapter import LMStudioError, LMStudioAdapter
from alice.core.application import AliceApplication
from alice.core.config import Config
from alice.planner.planner import TaskPlanner
from alice.tools.tools import BrowserOpenTool, Tool, ToolDispatcher, ToolRegistry


def make_app():
    config = Config()
    config.ai.base_url = "http://127.0.0.1:1234"
    config.ai.auto_start_server = False
    config.automation.auto_confirm_category_a = True
    config.automation.require_confirm_category_b = False
    config.automation.restricted_category_c = False
    with patch.object(LMStudioAdapter, "_request", return_value={}):
        app = AliceApplication(config)
    app.initialized = True
    return app


def test_planner_extracts_exact_chrome_search_query():
    planner = TaskPlanner(None)
    steps = planner.plan('open chrome and search for "Google ai studio"')

    assert len(steps) == 1
    assert steps[0].tool_name == "browser_open"
    assert steps[0].parameters["search"] == "Google ai studio"
    assert steps[0].parameters["visible"] is True


def test_planner_extracts_notepad_writing_text_and_target_window():
    planner = TaskPlanner(None)
    steps = planner.plan("open notepad and write my favourite color")

    assert [step.tool_name for step in steps] == ["open_app", "focus_app", "type_text"]
    assert steps[0].parameters == {"app_name": "notepad"}
    assert steps[2].parameters == {
        "text": "my favourite color",
        "target_window": "notepad",
    }


def test_empty_qwen_answer_falls_back_to_original_search_request():
    app = make_app()

    async def empty_answer(*_args, **_kwargs):
        raise LMStudioError(
            "LM Studio returned an empty user-facing answer. "
            "finish_reason='stop'; response fields=['content', 'reasoning_content', 'role', 'tool_calls']."
        )

    app.runtime.chat = empty_answer
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Chrome accepted the search URL."}
    )

    result = asyncio.run(app.chat_with_tools([
        {"role": "user", "content": 'open chrome and search for "Google ai studio"'}
    ]))

    app.tool_dispatcher.execute_async.assert_awaited_once_with(
        "browser_open", {"search": "Google ai studio", "visible": True}
    )
    assert "Completed 1 of 1" in result
    assert "Chrome accepted the search URL" in result


def test_empty_qwen_answer_does_not_claim_unknown_requests_were_executed():
    app = make_app()

    async def empty_answer(*_args, **_kwargs):
        raise LMStudioError("LM Studio returned an empty user-facing answer.")

    app.runtime.chat = empty_answer
    app.tool_dispatcher.execute_async = AsyncMock()

    result = asyncio.run(app.chat_with_tools([
        {"role": "user", "content": "Tell me something interesting"}
    ]))

    app.tool_dispatcher.execute_async.assert_not_awaited()
    assert "could not safely map" in result.lower()
    assert "no application or text action was performed" in result.lower()


def test_native_tool_call_rounds_continue_until_final_answer():
    app = make_app()
    responses = [
        json.dumps({
            "content": None,
            "tool_calls": [{
                "id": "open_1",
                "type": "function",
                "function": {"name": "open_app", "arguments": {"app_name": "notepad"}},
            }],
            "has_tool_calls": True,
        }),
        json.dumps({
            "content": None,
            "tool_calls": [{
                "id": "search_2",
                "type": "function",
                "function": {"name": "browser_open", "arguments": {"search": "Python docs"}},
            }],
            "has_tool_calls": True,
        }),
        "Both requested actions have been handled.",
    ]
    seen_messages = []

    async def fake_chat(messages, **_kwargs):
        seen_messages.append([dict(message) for message in messages])
        return responses.pop(0)

    app.runtime.chat = fake_chat
    app.tool_dispatcher.execute_async = AsyncMock(
        side_effect=[
            {"status": "success", "message": "Opened Notepad"},
            {"status": "success", "message": "Opened Google search"},
        ]
    )

    answer = asyncio.run(app.chat_with_tools([
        {"role": "user", "content": "Open notepad"}
    ]))

    assert answer == "Both requested actions have been handled."
    assert app.tool_dispatcher.execute_async.await_args_list[0].args == ("open_app", {"app_name": "notepad"})
    assert app.tool_dispatcher.execute_async.await_args_list[1].args == ("browser_open", {"search": "Python docs"})
    assert len(seen_messages) == 3

    # The empty JSON content field must stay empty, not be replaced by the raw
    # JSON tool-call envelope. Each model turn has one system prompt at index 0.
    first_assistant = next(m for m in seen_messages[1] if m.get("role") == "assistant")
    assert first_assistant["content"] == ""
    for messages in seen_messages:
        assert messages[0]["role"] == "system"
        assert sum(m.get("role") == "system" for m in messages) == 1
    assert any(m.get("tool_call_id") == "open_1" for m in seen_messages[1] if m["role"] == "tool")
    assert any(m.get("tool_call_id") == "search_2" for m in seen_messages[2] if m["role"] == "tool")


def test_dispatcher_limit_is_scoped_to_each_user_turn():
    app = make_app()
    app.tool_dispatcher.max_tool_calls = 1
    tool_response = json.dumps({
        "tool_calls": [{
            "id": "call_once",
            "type": "function",
            "function": {"name": "open_app", "arguments": '{"app_name":"notepad"}'},
        }],
        "has_tool_calls": True,
    })
    responses = [tool_response, "Done.", tool_response, "Done again."]

    async def fake_chat(*_args, **_kwargs):
        return responses.pop(0)

    app.runtime.chat = fake_chat
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Opened Notepad"}
    )

    first = asyncio.run(app.chat_with_tools([{"role": "user", "content": "Open notepad"}]))
    second = asyncio.run(app.chat_with_tools([{"role": "user", "content": "Open notepad"}]))

    assert first == "Done."
    assert second == "Done again."
    assert app.tool_dispatcher.execute_async.await_count == 2


def test_chrome_uses_persistent_dedicated_profile_and_encodes_search(monkeypatch, tmp_path):
    tool = BrowserOpenTool()
    tool._find_chrome_executable = lambda: r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    with patch("alice.tools.tools.subprocess.Popen") as popen:
        popen.return_value.pid = 9876
        result = tool.execute(search="Google ai studio")

    assert result["status"] == "success"
    assert result["verification"]["launch_requested"] is True
    assert result["verification"]["dedicated_profile"] is True
    assert result["verification"]["incognito"] is False
    command = popen.call_args.args[0]
    assert command[1].startswith("--user-data-dir=")
    assert command[1].endswith("ALICE/ChromeProfile") or command[1].endswith("ALICE\\ChromeProfile")
    assert command[-1] == "https://www.google.com/search?q=Google+ai+studio"
    assert not any("incognito" in str(arg).lower() for arg in command)
    assert not any("--user-data-dir" in str(arg).lower() and "alice" not in str(arg).lower() for arg in command)



def test_close_chrome_only_targets_alice_dedicated_profile(monkeypatch, tmp_path):
    import psutil
    from unittest.mock import MagicMock

    profile = tmp_path / "ALICE" / "ChromeProfile"
    monkeypatch.setattr(BrowserOpenTool, "_managed_profile_dir", str(profile))
    alice_process = MagicMock()
    alice_process.info = {
        "name": "chrome.exe",
        "cmdline": ["chrome.exe", f"--user-data-dir={profile}", "--type=browser"],
    }
    other_process = MagicMock()
    other_process.info = {
        "name": "chrome.exe",
        "cmdline": ["chrome.exe", r"--user-data-dir=C:\\Users\\Student\\AppData\\Local\\Google\\Chrome\\User Data"],
    }

    with patch("psutil.process_iter", return_value=[alice_process, other_process]), \
         patch("psutil.wait_procs", return_value=([alice_process], [])):
        result = BrowserOpenTool.close_owned_browser()

    assert result["status"] == "success"
    alice_process.terminate.assert_called_once()
    other_process.terminate.assert_not_called()


def test_planner_maps_explicit_close_chrome_to_owned_close_tool():
    steps = TaskPlanner(None).plan("close Chrome")
    assert len(steps) == 1
    assert steps[0].tool_name == "close_app"
    assert steps[0].parameters == {"app_name": "chrome"}



def test_chrome_launcher_does_not_claim_success_when_not_installed():
    tool = BrowserOpenTool()
    tool._find_chrome_executable = lambda: None
    result = tool.execute(search="Google ai studio")

    assert result["status"] == "error"
    assert "Chrome was not found" in result["error"]


def test_notepad_write_respects_category_b_permission():
    app = make_app()
    app.automation_config.require_confirm_category_b = True
    app.tool_dispatcher.execute_async = AsyncMock(
        return_value={"status": "success", "message": "Step ran"}
    )

    result = asyncio.run(app._execute_planned_tasks(
        [{"role": "user", "content": "open notepad and write my favourite color"}],
        "open notepad and write my favourite color",
        []
    ))

    called_tools = [call.args[0] for call in app.tool_dispatcher.execute_async.await_args_list]
    assert called_tools == ["open_app", "focus_app"]
    assert "permission" in result.lower()
    assert "did not claim the step was completed" in result.lower()


def test_chat_filters_old_system_messages_from_history():
    app = make_app()
    sent = []

    async def fake_chat(messages, **_kwargs):
        sent.append([dict(message) for message in messages])
        return "Hello."

    app.runtime.chat = fake_chat
    result = asyncio.run(app.chat_with_tools([
        {"role": "system", "content": "An old system prompt"},
        {"role": "user", "content": "Hi"},
    ]))

    assert result == "Hello."
    assert len([message for message in sent[0] if message.get("role") == "system"]) == 1
    assert sent[0][0]["content"] == app.system_prompt



def test_sync_tool_runs_off_the_async_event_loop_thread():
    class ThreadCheckingTool(Tool):
        def __init__(self):
            super().__init__("thread_check", "test")

        def execute(self, **_kwargs):
            return {"status": "success", "thread": threading.get_ident()}

    registry = ToolRegistry()
    registry.register(ThreadCheckingTool())
    dispatcher = ToolDispatcher(registry, Config())
    event_loop_thread = threading.get_ident()

    result = asyncio.run(dispatcher.execute_async("thread_check", {}))

    assert result["status"] == "success"
    assert result["thread"] != event_loop_thread
