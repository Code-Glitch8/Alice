#!/usr/bin/env python3
"""
SQLite database layer for ALICE.
Provides persistence for conversations, memory, tasks, projects, etc.
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional, Dict, Any


class AliceDatabase:
    """SQLite database manager for ALICE."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            db_path = Path.home() / ".alice" / "alice.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self.connection is None:
            self.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                uri=True
            )
            self.connection.row_factory = sqlite3.Row
            self._create_tables()
        return self.connection

    def _create_tables(self) -> None:
        """Create database tables."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT,
                model_used TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tool_calls TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            )
        """)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content_rowid='id',
                content='messages',
                tokenize='porter unicode61'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                category TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result TEXT,
                error TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                executable_path TEXT,
                alias TEXT,
                category TEXT,
                installed INTEGER DEFAULT 1
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        """)
        self.conn.commit()

    # Conversation methods
    def create_conversation(self, title: Optional[str] = None) -> int:
        """Create a new conversation."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute(
            "INSERT INTO conversations (created_at, updated_at, title) VALUES (?, ?, ?)",
            (now, now, title)
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_message(self, conversation_id: int, role: str, content: str,
                    tool_calls: Optional[str] = None) -> int:
        """Add a message to a conversation."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at, tool_calls) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, now, tool_calls)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))
        messages = [dict(r) for r in cursor.fetchall()]
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "title": row["title"],
            "status": row["status"],
            "messages": messages,
        }

    def search_memory(self, query: str) -> list:
        """Search memories using FTS5."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT m.* FROM messages m JOIN messages_fts f ON m.id = f.content_rowid "
            "WHERE messages_fts MATCH ?",
            (query,)
        )
        return [dict(r) for r in cursor.fetchall()]

    # Memory methods
    def save_memory(self, key: str, value: str, category: Optional[str] = None) -> int:
        """Save or update a memory."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute(
            """INSERT INTO memories (key, value, category, created_at, updated_at, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (key, value, category, now, now, "user")
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_memory(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a memory by key."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE key = ?", (key,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # Task methods
    def save_task(self, description: str, status: str = "pending") -> int:
        """Save a task."""
        cursor = self.conn.cursor()
        now = self._now()
        cursor.execute(
            "INSERT INTO tasks (description, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (description, status, now, now)
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_task(self, task_id: int, status: str, result: Optional[str] = None,
                    error: Optional[str] = None) -> None:
        """Update task status."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ?, updated_at = ?, result = ?, error = ? WHERE id = ?",
            (status, self._now(), result, error, task_id)
        )
        self.conn.commit()

    # Preference methods
    def get_preference(self, key: str, default: str = "null") -> str:
        """Get a user preference."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row is None:
            return default
        if default == "null":
            return row["value"]
        return row["value"] if row["value"] == default else row["value"]

    def set_preference(self, key: str, value: str) -> None:
        """Set a user preference."""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO user_preferences (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value)
        )
        self.conn.commit()

    @staticmethod
    def _now() -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()

    def close(self) -> None:
        """Close database connection."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None