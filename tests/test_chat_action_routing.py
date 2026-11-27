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
    "user_request,folder_name,file_name,location",
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
    user_request, folder_name, file_name, location, monkeypatch, tmp_path
):
    from alice.core import config as config_module

    monkeypatch.setattr(
        config_module,
        "get_windows_known_folder",
        lambda requested: tmp_path / requested,
    )

    steps = _planner().plan(user_request)

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


def test_hierarchical_create_request_plans_all_subfolders_and_files(monkeypatch, tmp_path):
    from alice.core import config as config_module

    monkeypatch.setattr(
        config_module,
        "get_windows_known_folder",
        lambda requested: tmp_path / requested,
    )
    request = (
        "create a folder named ALICE_Complex_Test on my Desktop, "
        "create subfolders Documents, Research and Reports inside it, "
        "create task_log.txt inside Documents, "
        "create research_links.txt inside Research, "
        "create summary.txt inside Reports"
    )

    steps = _planner().legacy_planner.plan(request)

    assert [step.tool_name for step in steps] == [
        "create_folder", "create_folder", "create_folder", "create_folder",
        "write_file", "write_file", "write_file",
    ]
    root = tmp_path / "Desktop" / "ALICE_Complex_Test"
    assert steps[0].parameters["path"] == str(root)
    assert [Path(step.parameters["path"]).name for step in steps[1:4]] == [
        "Documents", "Research", "Reports",
    ]
    assert Path(steps[4].parameters["path"]) == root / "Documents" / "task_log.txt"
    assert Path(steps[5].parameters["path"]) == root / "Research" / "research_links.txt"
    assert Path(steps[6].parameters["path"]) == root / "Reports" / "summary.txt"


def test_subfolder_followup_uses_previously_created_folder(tmp_path):
    root = tmp_path / "ALICE_Complex_Test"
    request = (
        "create subfolders Documents, Research and Reports inside it, "
        "create task_log.txt inside Documents"
    )

    steps = _planner().legacy_planner.plan(request, context_folder=str(root))

    assert [step.tool_name for step in steps] == [
        "create_folder", "create_folder", "create_folder", "write_file",
    ]
    assert Path(steps[0].parameters["path"]) == root / "Documents"
    assert Path(steps[1].parameters["path"]) == root / "Research"
    assert Path(steps[2].parameters["path"]) == root / "Reports"
    assert Path(steps[3].parameters["path"]) == root / "Documents" / "task_log.txt"


def test_search_for_folder_in_drive_extracts_query_and_scope():
    steps = _planner().legacy_planner.plan("search for the Alice folder in D:\\\\")

    assert len(steps) == 1
    assert steps[0].tool_name == "search_files"
    assert steps[0].parameters["query"] == "Alice"
    assert steps[0].parameters["folder"] == "D:\\\\"


def test_find_app_uses_a_close_installed_name_but_rejects_unrelated_names(monkeypatch):
    from alice.computer.engine import ComputerEngine

    engine = ComputerEngine.__new__(ComputerEngine)
    engine.running_apps = []
    monkeypatch.setattr(engine, "_get_start_menu_paths", lambda: [])
    monkeypatch.setattr(engine, "list_installed_apps", lambda: [
        {"name": "Discord", "path": r"C:\Program Files\Discord\Discord.exe", "type": "start_menu"},
        {"name": "Project Pilot", "path": r"C:\Program Files\Project Pilot\pilot.exe", "type": "start_menu"},
    ])

    result = engine.find_app("discard")
    project_result = engine.find_app("project pilat")

    assert result is not None and result["name"] == "Discord"
    assert project_result is not None and project_result["name"] == "Project Pilot"
    assert engine.find_app("totally-unrelated-app-name") is None


@pytest.mark.asyncio
async def test_file_search_request_is_executed_without_model_tool_loop():
    app = AliceApplication.__new__(AliceApplication)
    app.initialized = True
    app.automation_config = SimpleNamespace(max_tool_calls=5)
    app.system_prompt = "test"
    app.task_planner = _planner()
    app.tool_dispatcher = SimpleNamespace(call_count=0)
    app.get_tools_for_api = lambda: []
    app.runtime = SimpleNamespace(chat=AsyncMock(side_effect=AssertionError("model should not be called")))
    app._execute_planned_tasks = AsyncMock(return_value="Found 0 files")

    result = await AliceApplication.chat_with_tools(
        app, [{"role": "user", "content": "search for the Alice folder in D:\\\\"}]
    )

    assert result == "Found 0 files"
    app.runtime.chat.assert_not_awaited()
    steps = app._execute_planned_tasks.await_args.kwargs["planned_steps"]
    assert steps[0].tool_name == "search_files"
    assert steps[0].parameters["query"] == "Alice"


@pytest.mark.asyncio
async def test_continue_replays_only_the_previous_read_only_search():
    app = AliceApplication.__new__(AliceApplication)
    app.initialized = True
    app.automation_config = SimpleNamespace(max_tool_calls=5)
    app.system_prompt = "test"
    app.task_planner = _planner()
    app.tool_dispatcher = SimpleNamespace(call_count=0)
    app.get_tools_for_api = lambda: []
    app.runtime = SimpleNamespace(chat=AsyncMock(side_effect=AssertionError("model should not be called")))
    app._execute_planned_tasks = AsyncMock(return_value="Search completed")

    history = [
        {"role": "user", "content": "search for the Alice folder in D:\\\\"},
        {"role": "assistant", "content": "The search was interrupted."},
        {"role": "user", "content": "continue"},
    ]
    result = await AliceApplication.chat_with_tools(app, history)

    assert result == "Search completed"
    app.runtime.chat.assert_not_awaited()
    steps = app._execute_planned_tasks.await_args.kwargs["planned_steps"]
    assert steps[0].tool_name == "search_files"



@pytest.mark.asyncio
async def test_subfolder_followup_uses_confirmed_folder_from_conversation_history(tmp_path):
    app = AliceApplication.__new__(AliceApplication)
    app.initialized = True
    app.automation_config = SimpleNamespace(max_tool_calls=5)
    app.system_prompt = "test"
    app.task_planner = _planner()
    app.tool_dispatcher = SimpleNamespace(call_count=0)
    app.get_tools_for_api = lambda: []
    app.runtime = SimpleNamespace(chat=AsyncMock(side_effect=AssertionError("model should not be called")))
    app._execute_planned_tasks = AsyncMock(return_value="Created all requested children")
    root = tmp_path / "ALICE_Complex_Test"

    history = [
        {"role": "user", "content": "create a folder named ALICE_Complex_Test on my Desktop"},
        {"role": "assistant", "content": f"Created folder: {root}"},
        {"role": "user", "content": "create subfolders Documents, Research and Reports inside it, create task_log.txt inside Documents"},
    ]
    result = await AliceApplication.chat_with_tools(app, history)

    assert result == "Created all requested children"
    app.runtime.chat.assert_not_awaited()
    steps = app._execute_planned_tasks.await_args.kwargs["planned_steps"]
    assert [step.tool_name for step in steps] == [
        "create_folder", "create_folder", "create_folder", "write_file",
    ]
    assert Path(steps[3].parameters["path"]) == root / "Documents" / "task_log.txt"


def test_alice_wake_word_prefix_does_not_disable_deterministic_create_routing():
    app = AliceApplication.__new__(AliceApplication)
    assert app._is_deterministic_filesystem_request(
        "ALICE, create a folder named ALICE_Complex_Test on my Desktop, create subfolders Documents"
    )
    assert app._is_deterministic_search_request("ALICE, search for the Alice folder in D:\\\\")
