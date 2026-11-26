"""Tests for ALICE's Computer Access Manager and scoped file operations."""
from pathlib import Path
from types import SimpleNamespace

from alice.core.access_manager import ComputerAccessManager, is_within
from alice.computer.file_operations import FileOperations
from alice.core.application import AliceApplication
from alice.tools.tools import create_default_tools


def make_config(root, **overrides):
    values = {
        "allowed_locations": [str(root)],
        "search_all_drives": False,
        "allow_read_files": True,
        "allow_create_files_folders": True,
        "allow_edit_files": True,
        "allow_move_files": True,
        "allow_app_control": True,
        "allow_delete_files": True,
        "require_confirmation_for_destructive": True,
        "auto_confirm_category_a": True,
        "require_confirm_category_b": False,
        "restricted_category_c": True,
        "max_tool_calls": 5,
    }
    values.update(overrides)
    return SimpleNamespace(automation=SimpleNamespace(**values))


def test_path_scope_uses_path_components_not_string_prefix(tmp_path):
    allowed = tmp_path / "allowed"
    sibling = tmp_path / "allowed-evil"
    allowed.mkdir()
    sibling.mkdir()
    assert is_within(allowed / "file.txt", allowed)
    assert not is_within(sibling / "file.txt", allowed)


def test_manager_uses_configured_roots_when_all_drive_search_is_off(tmp_path):
    manager = ComputerAccessManager(make_config(tmp_path))
    assert manager.path_allowed(tmp_path / "notes.txt")
    outside = tmp_path.parent / "outside.txt"
    assert not manager.path_allowed(outside)


def test_manager_respects_feature_toggles(tmp_path):
    config = make_config(tmp_path, allow_read_files=False, allow_move_files=False)
    manager = ComputerAccessManager(config)
    assert not manager.permission_enabled("read_file")
    assert not manager.permission_enabled("move_file")
    assert manager.permission_enabled("create_folder")


def test_file_operations_reads_and_moves_inside_scope(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("ALICE test", encoding="utf-8")
    operations = FileOperations(make_config(tmp_path))

    ok, content, details = operations.read_file(str(source))
    assert ok and content == "ALICE test"
    assert details["path"] == str(source.resolve())

    destination = tmp_path / "archive" / "source.txt"
    ok, message, details = operations.move_file(str(source), str(destination))
    assert ok
    assert destination.read_text(encoding="utf-8") == "ALICE test"
    assert not source.exists()


def test_file_operations_refuses_move_outside_scope(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    source = allowed / "source.txt"
    source.write_text("safe", encoding="utf-8")
    operations = FileOperations(make_config(allowed))
    ok, message, _ = operations.move_file(str(source), str(outside / "source.txt"))
    assert not ok
    assert source.exists()


def test_read_and_move_tools_are_registered():
    registry = create_default_tools()
    assert registry.get("read_file") is not None
    assert registry.get("move_file") is not None


def test_destructive_action_always_asks_even_when_category_b_is_auto_allowed(tmp_path):
    app = AliceApplication.__new__(AliceApplication)
    config = make_config(tmp_path)
    app.config = config
    app.automation_config = config.automation
    calls = []

    def confirm(tool_name, description):
        calls.append((tool_name, description))
        return True

    app.permission_confirmation_callback = confirm
    tool = SimpleNamespace(name="delete_file", required_permission="B")
    import asyncio
    allowed = asyncio.run(app._is_action_permitted(tool, "Delete file", {"path": str(tmp_path / "important.txt")}))
    assert allowed
    assert calls and calls[0][0] == "delete_file"
    assert str(tmp_path / "important.txt") in calls[0][1]


def test_destructive_action_is_denied_without_confirmation_callback(tmp_path):
    app = AliceApplication.__new__(AliceApplication)
    config = make_config(tmp_path)
    app.config = config
    app.automation_config = config.automation
    app.permission_confirmation_callback = None
    tool = SimpleNamespace(name="delete_file", required_permission="B")
    import asyncio
    assert not asyncio.run(app._is_action_permitted(tool, "Delete file", {"path": str(tmp_path / "file.txt")}))


def test_overwrite_requires_confirmation_but_new_file_does_not(tmp_path):
    app = AliceApplication.__new__(AliceApplication)
    config = make_config(tmp_path)
    app.config = config
    app.automation_config = config.automation
    calls = []
    app.permission_confirmation_callback = lambda name, description: calls.append((name, description)) or True
    tool = SimpleNamespace(name="write_file", required_permission="B")
    import asyncio

    existing = tmp_path / "existing.txt"
    existing.write_text("old", encoding="utf-8")
    assert asyncio.run(app._is_action_permitted(tool, "Write file", {"path": str(existing), "content": "new"}))
    assert len(calls) == 1 and "existing.txt" in calls[0][1]

    calls.clear()
    assert asyncio.run(app._is_action_permitted(tool, "Create file", {"path": str(tmp_path / "new.txt"), "content": "new"}))
    assert calls == []
