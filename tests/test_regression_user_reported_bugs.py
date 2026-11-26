"""Regression tests for ALICE Windows path, search, and intent fixes."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from alice.computer.file_operations import FileOperations
from alice.planner.planner import TaskPlanner
from alice.tools.tools import create_default_tools


def test_search_finds_hidden_cache_directories(tmp_path):
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()
    (cache / "README.md").write_text("cache", encoding="utf-8")

    config = SimpleNamespace(
        automation=SimpleNamespace(allowed_locations=[str(tmp_path)])
    )
    results = FileOperations(config).search_files(".pytest_cache")

    assert any(item["path"] == str(cache) and item["type"] == "directory" for item in results)


def test_search_accepts_nested_folder_inside_allowed_root(tmp_path):
    nested = tmp_path / "Projects" / "Alice"
    nested.mkdir(parents=True)
    (nested / "target.txt").write_text("ok", encoding="utf-8")

    config = SimpleNamespace(
        automation=SimpleNamespace(allowed_locations=[str(tmp_path)])
    )
    results = FileOperations(config).search_files("target", str(nested))

    assert any(Path(item["path"]).name == "target.txt" for item in results)


def test_search_rejects_folder_outside_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("no", encoding="utf-8")

    config = SimpleNamespace(
        automation=SimpleNamespace(allowed_locations=[str(allowed)])
    )
    assert FileOperations(config).search_files("secret", str(outside)) == []


def test_list_installed_apps_is_registered():
    assert create_default_tools().get("list_installed_apps") is not None


def test_planner_routes_app_inventory_to_list_tool():
    planner = TaskPlanner(tool_registry=None)
    steps = planner.plan("list all the apps on my PC")
    assert len(steps) == 1
    assert steps[0].tool_name == "list_installed_apps"


def test_planner_generates_note_instead_of_pasting_instruction():
    planner = TaskPlanner(tool_registry=None)
    steps = planner.plan("open notepad and write a short note on cows")

    assert [step.tool_name for step in steps] == [
        "open_app", "focus_app", "keyboard_shortcut", "type_text"
    ]
    assert steps[-1].parameters["generate_topic"] == "cows"
    assert "text" not in steps[-1].parameters


def test_planner_preserves_explicit_quoted_text():
    planner = TaskPlanner(tool_registry=None)
    steps = planner.plan('open notepad and type "Hello there"')

    assert steps[-1].tool_name == "type_text"
    assert steps[-1].parameters["text"] == "Hello there"


def test_packaged_app_alias_resolves_to_a_string_command():
    from alice.computer.engine import ComputerEngine

    command = ComputerEngine()._find_uwp_app("microsoft store")
    assert command == "ms-windows-store:"
    assert isinstance(command, str)


@pytest.mark.skipif(os.name != "nt", reason="Windows Known Folder API test")
def test_downloads_known_folder_resolves_to_a_real_path():
    from alice.core.config import get_windows_known_folder

    downloads = get_windows_known_folder("Downloads")
    assert downloads is not None
    assert downloads.is_absolute()
    assert "C:\\Users\\user" not in str(downloads)
