"""Regression coverage for ALICE CLI action routing and tool-loop termination."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from alice.core.application import AliceApplication
from alice.planner.planner import TaskPlanner
from alice.tools.tools import create_default_tools


def _planner():
    return TaskPlanner(tool_registry=create_default_tools())


def test_open_youtube_is_routed_to_browser():
    steps = _planner().plan("open youtube")

    assert len(steps) == 1
    assert steps[0].tool_name == "browser_open"
    assert steps[0].parameters["url"] == "youtube"


def test_open_chrome_is_routed_to_browser():
    steps = _planner().plan("open chrome")

    assert len(steps) == 1
    assert steps[0].tool_name == "browser_open"


def test_open_notepad_is_routed_to_desktop_app():
    steps = _planner().plan("open notepad")

    assert len(steps) == 1
    assert steps[0].tool_name == "open_app"
    assert steps[0].parameters["app_name"] == "notepad"


@pytest.mark.parametrize(
    "request,folder_name,file_name,location",
    [
        (
            "create a folder called Homework with a text file named notes.txt inside on my Desktop",
            "Homework", "notes.txt", "Desktop",
        ),
        (
            "make a folder named Physics Notes containing a text file called summary.txt in Documents",
            "Physics Notes", "summary.txt", "Documents",
        ),
        (
            "create a folder with a text file inside",
            "NewFolder", "notes.txt", "Desktop",
        ),
    ],
)
def test_compound_folder_and_text_file_plan(
    request, folder_name, file_name, location, monkeypatch, tmp_path
):
    from alice.core import config as config_module

    monkeypatch.setattr(
        config_module,
        "get_windows_known_folder",
        lambda requested: tmp_path / requested,
    )

    steps = _planner().plan(request)

    assert [step.tool_name for step in steps] == ["create_folder", "write_file"]
    created_folder = Path(steps[0].parameters["path"])
    created_file = Path(steps[1].parameters["path"])
    assert created_folder.name == folder_name
    assert created_file.name == file_name
    assert created_file.parent == created_folder
    assert location in str(created_folder)


@pytest.mark.asyncio
async def test_explicit_open_request_uses_planner_without_model_loop():
    app = AliceApplication.__new__(AliceApplication)
    app.initialized = True
    app.automation_config = SimpleNamespace(max_tool_calls=5)
    app.system_prompt = "test"
    app.task_planner = _planner()
    app.tool_dispatcher = SimpleNamespace(call_count=0)
    app.get_tools_for_api = lambda: []
    app.runtime = SimpleNamespace(chat=AsyncMock(side_effect=AssertionError("model should not be called")))
    app._execute_planned_tasks = AsyncMock(return_value="Completed 1 of 1 planned step(s).")

    result = await AliceApplication.chat_with_tools(
        app, [{"role": "user", "content": "open notepad"}]
    )

    assert result.startswith("Completed 1")
    app.runtime.chat.assert_not_awaited()
    planned_steps = app._execute_planned_tasks.await_args.kwargs["planned_steps"]
    assert planned_steps[0].tool_name == "open_app"


@pytest.mark.asyncio
async def test_single_successful_side_effect_tool_ends_chat_loop():
    tool_call = {
        "id": "call-open",
        "type": "function",
        "function": {"name": "browser_open", "arguments": json.dumps({"url": "youtube"})},
    }
    model_response = json.dumps({
        "has_tool_calls": True,
        "content": None,
        "tool_calls": [tool_call],
    })
    app = AliceApplication.__new__(AliceApplication)
    app.initialized = True
    app.automation_config = SimpleNamespace(max_tool_calls=5)
    app.system_prompt = "test"
    app.tool_dispatcher = SimpleNamespace(call_count=0)
    app.get_tools_for_api = lambda: []
    app.runtime = SimpleNamespace(chat=AsyncMock(return_value=model_response))
    app._execute_tool_calls = AsyncMock(return_value=[{
        "role": "tool",
        "tool_call_id": "call-open",
        "content": json.dumps({"status": "success", "message": "Opened YouTube"}),
    }])

    result = await AliceApplication.chat_with_tools(
        app, [{"role": "user", "content": "navigate to youtube"}]
    )

    assert result == "Done. Opened YouTube"
    assert app.runtime.chat.await_count == 1
