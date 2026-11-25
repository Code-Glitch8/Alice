#!/usr/bin/env python3
"""
Test suite for ALICE components.
"""

import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()