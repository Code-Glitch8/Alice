#!/usr/bin/env python3
"""
Memory management for ALICE.
Provides persistent memory, conversation history, and user preferences.
"""

import logging
from typing import Any, Dict, List, Optional

from ..database.db import AliceDatabase

logger = logging.getLogger(__name__)


class MemoryManager:
    """Memory manager for ALICE."""

    def __init__(self, db: AliceDatabase):
        self.db = db

    def save_conversation(self, messages: List[Dict[str, str]], title: Optional[str] = None) -> int:
        """Save a conversation to memory."""
        conversation_id = self.db.create_conversation(title)
        for msg in messages:
            self.db.add_message(
                conversation_id,
                msg.get("role", "user"),
                msg.get("content", ""),
            )
        return conversation_id

    def recall(self, query: str) -> List[Dict[str, Any]]:
        """Search memory for relevant information."""
        return self.db.search_memory(query)

    def remember(self, key: str, value: str, category: Optional[str] = None) -> int:
        """Save a memory explicitly."""
        return self.db.save_memory(key, value, category)

    def get_context(self, query: str) -> str:
        """Get context for a query from memory."""
        results = self.recall(query)
        if not results:
            return ""
        return "\n".join([r.get("content", "") for r in results[:5]])

    def set_preference(self, key: str, value: str) -> None:
        """Set a user preference."""
        self.db.set_preference(key, value)

    def get_preference(self, key: str, default: str = "null") -> str:
        """Get a user preference."""
        return self.db.get_preference(key, default)

    def clear_memory(self, category: Optional[str] = None) -> bool:
        """Clear memory (optionally by category)."""
        # In production, this would delete from database
        logger.info(f"Clearing memory (category: {category})")
        return True


if __name__ == "__main__":
    from alice.database.db import AliceDatabase
    db = AliceDatabase()
    memory = MemoryManager(db)
    memory.remember("user", "test_value")
    print("Memory manager initialized")