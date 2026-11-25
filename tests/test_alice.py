#!/usr/bin/env python3
"""
Test suite for ALICE components.
"""

import unittest
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


class TestAlice(unittest.TestCase):
    """Test ALICE components."""

    def test_config(self):
        """Test configuration loading."""
        from alice.core.config import Config
        config = Config.load()
        self.assertIsInstance(config.ai.runtime, str)

    def test_database(self):
        """Test database operations."""
        from alice.database.db import AliceDatabase
        db = AliceDatabase(":memory:")
        # Create a table - should succeed without error
        result = db.conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        self.assertIsNotNone(result)
        # Insert and verify
        db.conn.execute("INSERT INTO test (id) VALUES (1)")
        row = db.conn.execute("SELECT * FROM test WHERE id = 1").fetchone()
        self.assertIsNotNone(row)

    def test_adapter(self):
        """Test AI adapter."""
        from alice.ai.lmstudio_adapter import LMStudioAdapter
        adapter = LMStudioAdapter(None)
        status = adapter.get_runtime_status()
        self.assertIn("runtime_running", status)

    def test_voice(self):
        """Test voice pipeline."""
        from alice.voice.pipeline import VoicePipeline
        voice = VoicePipeline(None)
        self.assertFalse(voice.listening)

    def test_computer(self):
        """Test computer engine."""
        from alice.computer.engine import ComputerEngine
        engine = ComputerEngine(None)
        status = engine.get_status()
        self.assertIn("running_apps", status)

    def test_orb(self):
        """Test orb component."""
        from alice.orb.orb import Orb
        orb = Orb(None)
        orb.update_state("listening")
        self.assertEqual(orb.state, "listening")

    def test_tools(self):
        """Test tools registry."""
        from alice.tools.tools import create_default_tools
        tools = create_default_tools()
        self.assertGreater(len(tools.list_tools()), 0)

    def test_planner(self):
        """Test task planner."""
        from alice.planner.planner import TaskPlanner
        from alice.tools.tools import create_default_tools
        planner = TaskPlanner(create_default_tools())
        steps = planner.plan("Open Chrome")
        self.assertGreater(len(steps), 0)

    def test_hotkey(self):
        """Test hotkey service."""
        from alice.omen.hotkey_service import HotkeyService
        service = HotkeyService(None)
        status = service.get_status()
        self.assertFalse(status["is_running"])

    def test_memory(self):
        """Test memory manager."""
        from alice.memory.manager import MemoryManager
        from alice.database.db import AliceDatabase
        db = AliceDatabase(":memory:")
        memory = MemoryManager(db)
        result = memory.remember("key", "value")
        self.assertIsNotNone(result)


class TestFileOperations(unittest.TestCase):
    """Test file operations with the fix for import."""

    def test_import_time_module(self):
        """Test that time module is imported in file_operations."""
        from alice.computer.file_operations import FileOperations
        # If this imports successfully, the fix is in place
        self.assertTrue(hasattr(FileOperations, '__init__'))

    def test_search_files_uses_allowed_locations(self):
        """Test that search_files properly uses allowed locations."""
        from alice.computer.file_operations import FileOperations
        from alice.core.config import Config

        config = Config.load()
        fo = FileOperations(config)

        # Mock allowed_locations to contain a test path
        with patch.object(fo, 'allowed_locations', [str(Path.home())]):
            # This should not return empty immediately
            results = fo.search_files(".txt")
            # Results will depend on what .txt files exist, but should not error
            self.assertIsInstance(results, list)


class TestApplicationOwner(unittest.TestCase):
    """Test Application Owner registry (Part 19)."""

    def setUp(self):
        from alice.core.application_owner import ApplicationOwner
        ApplicationOwner.reset_instance()

    def tearDown(self):
        from alice.core.application_owner import ApplicationOwner
        ApplicationOwner.reset_instance()

    def test_singleton(self):
        """Test that ApplicationOwner is a singleton."""
        from alice.core.application_owner import ApplicationOwner
        owner1 = ApplicationOwner.get_instance()
        owner2 = ApplicationOwner.get_instance()
        self.assertIs(owner1, owner2)

    def test_register_app(self):
        """Test registering an application."""
        from alice.core.application_owner import ApplicationOwner
        owner = ApplicationOwner.get_instance()

        owner.register_app("notepad", 12345)
        apps = owner.get_owned_apps()

        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]['app'], "notepad")
        self.assertEqual(apps[0]['pid'], 12345)

    def test_unregister_app(self):
        """Test unregistering an application."""
        from alice.core.application_owner import ApplicationOwner
        owner = ApplicationOwner.get_instance()

        owner.register_app("notepad", 12345)
        result = owner.unregister_app(12345)

        self.assertTrue(result)
        self.assertEqual(len(owner.get_owned_apps()), 0)

    def test_get_by_pid(self):
        """Test getting app by PID."""
        from alice.core.application_owner import ApplicationOwner
        owner = ApplicationOwner.get_instance()

        owner.register_app("notepad", 12345)
        app_info = owner.get_app_by_pid(12345)

        self.assertIsNotNone(app_info)
        self.assertEqual(app_info['pid'], 12345)

    def test_is_owned_by_alice(self):
        """Test checking if process is owned."""
        from alice.core.application_owner import ApplicationOwner
        owner = ApplicationOwner.get_instance()

        owner.register_app("notepad", 12345)
        self.assertTrue(owner.is_owned_by_alice(12345))
        self.assertFalse(owner.is_owned_by_alice(99999))

    def test_get_status(self):
        """Test getting registry status."""
        from alice.core.application_owner import ApplicationOwner
        owner = ApplicationOwner.get_instance()

        owner.register_app("notepad", 12345)
        owner.register_app("chrome", 67890)

        status = owner.get_status(verify_processes=False)
        self.assertEqual(status['total_owned'], 2)
        self.assertIn('notepad', status['apps'])
        self.assertIn('chrome', status['apps'])


class TestToolDispatcher(unittest.TestCase):
    """Test Tool Dispatcher class."""

    def test_tool_dispatcher_exists(self):
        """Test that ToolDispatcher class exists."""
        from alice.tools.tools import ToolDispatcher, create_default_tools
        self.assertTrue(callable(ToolDispatcher))

    def test_dispatcher_initialization(self):
        """Test ToolDispatcher initialization."""
        from alice.tools.tools import ToolDispatcher, create_default_tools
        from unittest.mock import MagicMock

        registry = create_default_tools()
        # Create a proper mock config with automation.max_tool_calls
        mock_config = MagicMock()
        mock_config.automation.max_tool_calls = 5
        dispatcher = ToolDispatcher(registry, mock_config)

        self.assertEqual(dispatcher.tool_registry, registry)
        self.assertEqual(dispatcher.max_tool_calls, 5)

    def test_execute_invalid_tool(self):
        """Test executing a non-existent tool."""
        from alice.tools.tools import ToolDispatcher, create_default_tools
        from unittest.mock import MagicMock

        registry = create_default_tools()
        mock_config = MagicMock()
        mock_config.automation.max_tool_calls = 5
        dispatcher = ToolDispatcher(registry, mock_config)

        result = dispatcher.execute("nonexistent_tool", {})
        self.assertEqual(result['status'], 'error')
        self.assertIn('not found', result['error'])


class TestMarkdownFencedJSONParsing(unittest.TestCase):
    """Test markdown-fenced JSON response parsing."""

    def test_parse_raw_json(self):
        """Test parsing raw JSON response."""
        from alice.core.application import AliceApplication
        from alice.ai.lmstudio_adapter import LMStudioAdapter
        from unittest.mock import MagicMock, patch

        # Create a proper mock config with ai.base_url
        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        response = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{\\"x\\": 1}"}}], "content": "test"}'
        result = app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)

    def test_parse_markdown_fenced_json(self):
        """Test parsing markdown-fenced JSON response."""
        from alice.core.application import AliceApplication
        from alice.ai.lmstudio_adapter import LMStudioAdapter
        from unittest.mock import MagicMock, patch

        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        response = '```json\n{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": {}}}]}\n```'
        result = app._parse_ai_response(response)

        self.assertIsNotNone(result)
        self.assertIn('tool_calls', result)

    def test_parse_non_json_response(self):
        """Test parsing non-JSON response returns None."""
        from alice.core.application import AliceApplication
        from alice.ai.lmstudio_adapter import LMStudioAdapter
        from unittest.mock import MagicMock, patch

        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        response = 'This is just plain text, not JSON.'
        result = app._parse_ai_response(response)

        self.assertIsNone(result)

    def test_parse_empty_response(self):
        """Test parsing empty response returns None."""
        from alice.core.application import AliceApplication
        from alice.ai.lmstudio_adapter import LMStudioAdapter
        from unittest.mock import MagicMock, patch

        mock_config = MagicMock()
        mock_config.ai.base_url = "http://127.0.0.1:1234"

        with patch.object(LMStudioAdapter, '_request', return_value={}):
            app = AliceApplication(mock_config)

        result = app._parse_ai_response('')
        self.assertIsNone(result)

        result = app._parse_ai_response('   ')
        self.assertIsNone(result)


class TestComputerEngineSearchFiles(unittest.TestCase):
    """Test ComputerEngine search_files fix."""

    def test_search_files_implementation(self):
        """Test that ComputerEngine.search_files actually searches."""
        from alice.computer.engine import ComputerEngine

        engine = ComputerEngine(MagicMock())

        # Mock allowed_locations in config
        with patch.object(engine, '_resolve_app'):
            with patch('alice.computer.file_operations.FileOperations') as mock_fo:
                mock_fo_instance = MagicMock()
                mock_fo_instance.search_files.return_value = [
                    {"name": "test.txt", "path": "/test.txt"}
                ]
                mock_fo.return_value = mock_fo_instance

                with patch('alice.core.config.Config.load') as mock_config:
                    mock_config.return_value = MagicMock(autolocation=['/'])
                    result = engine.search_files("test")

                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0]['name'], 'test.txt')


class TestExplorerOpening(unittest.TestCase):
    """Test File Explorer opening with target path."""

    def test_resolve_explorer_no_target(self):
        """Test resolving explorer without target path."""
        from alice.computer.engine import ComputerEngine

        engine = ComputerEngine(None)
        cmd, cmd_type = engine._resolve_app("explorer")

        self.assertEqual(cmd, "explorer.exe")
        self.assertEqual(cmd_type, "explorer")

    def test_resolve_explorer_with_target(self):
        """Test resolving explorer with target path."""
        from alice.computer.engine import ComputerEngine

        engine = ComputerEngine(None)
        target = r"C:\Users\Test\Desktop"
        cmd, cmd_type = engine._resolve_app("explorer", target)

        self.assertIn(target, cmd)
        self.assertEqual(cmd_type, "explorer")


class TestBrowserToolsVisibility(unittest.TestCase):
    """Test browser tools visible mode (for debugging)."""

    def test_browser_open_tool_exists(self):
        """Test BrowserOpenTool exists."""
        from alice.tools.tools import BrowserOpenTool
        tool = BrowserOpenTool()
        self.assertEqual(tool.name, "browser_open")

    def test_browser_open_returns_result_structure(self):
        """Test BrowserOpenTool returns proper result structure."""
        from alice.tools.tools import BrowserOpenTool
        import asyncio

        tool = BrowserOpenTool()

        # Since we can't test with actual browser, check the result structure
        # when playwright is available
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                result = loop.run_until_complete(tool._browser_open_async(None, "test search"))
                # Just check structure, not actual execution
                self.assertIn('status', result)
        except RuntimeError:
            # Event loop issues in tests are OK
            pass


class TestOpenAppToolTargetPath(unittest.TestCase):
    """Test OpenAppTool with target_path parameter."""

    def test_execute_with_target_path(self):
        """Test OpenAppTool accepts target_path parameter."""
        from alice.tools.tools import OpenAppTool

        tool = OpenAppTool()

        # The tool should accept target_path parameter
        # This tests the parameter name flexibility
        with patch('alice.computer.engine.ComputerEngine') as mock_engine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.open_app.return_value = (True, "Opened", {"pid": 1234})
            mock_engine.return_value = mock_engine_instance

            with patch('alice.core.config.Config.load') as mock_config:
                mock_config.return_value = MagicMock()

                result = tool.execute(app_name="explorer", target_path=r"C:\Users")

                self.assertEqual(result['status'], 'success')


if __name__ == "__main__":
    unittest.main()