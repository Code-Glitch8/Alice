#!/usr/bin/env python3
"""
Context Window Management for ALICE.

Manages token budgets and conversation history to prevent context overflow.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: str
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            token_count=data.get("token_count", 0),
        )


@dataclass
class ToolResult:
    """Result from a tool call."""
    tool_name: str
    result: Any
    timestamp: str
    token_count: int = 0
    is_success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "result": self.result,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "is_success": self.is_success,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        return cls(
            tool_name=data["tool_name"],
            result=data["result"],
            timestamp=data["timestamp"],
            token_count=data.get("token_count", 0),
            is_success=data.get("is_success", True),
        )

    @property
    def summarized(self) -> str:
        """Return a compact summary of the result."""
        if isinstance(self.result, str):
            content = self.result[:200] if len(self.result) > 200 else self.result
            return f"{self.tool_name}: {content}..."
        elif isinstance(self.result, dict):
            return f"{self.tool_name}: {json.dumps(self.result, separators=(',', ':'))[:200]}..."
        elif isinstance(self.result, list):
            return f"{self.tool_name}: list of {len(self.result)} items"
        return f"{self.tool_name}: executed successfully"


@dataclass
class ContextEntry:
    """An entry in the context history."""
    turn: Optional[ConversationTurn] = None
    tool_result: Optional[ToolResult] = None
    importance: float = 0.5  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        data = {"importance": self.importance}
        if self.turn:
            data["turn"] = self.turn.to_dict()
        if self.tool_result:
            data["tool_result"] = self.tool_result.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEntry":
        return cls(
            turn=ConversationTurn.from_dict(data["turn"]) if data.get("turn") else None,
            tool_result=ToolResult.from_dict(data["tool_result"]) if data.get("tool_result") else None,
            importance=data.get("importance", 0.5),
        )


class ContextManager:
    """
    Manages the conversation context window for token budget compliance.

    Features:
    - Tracks token usage when available
    - Prioritizes turns by importance
    - Summarizes older turns to fit budget
    - Handles context overflow gracefully
    """

    def __init__(
        self,
        max_context_tokens: int = 6000,
        reserve_tokens: int = 2192,
        system_prompt_tokens: int = 1500,
        model_name: str = "qwen3.5-4b",
    ):
        """
        Initialize the Context Manager.

        Args:
            max_context_tokens: Maximum tokens to use in context (default 6000 for Qwen3.5-4B)
            reserve_tokens: Tokens to reserve for responses (default 2192)
            system_prompt_tokens: Approximate system prompt tokens
            model_name: Name of the model being used
        """
        self.max_context_tokens = max_context_tokens
        self.reserve_tokens = reserve_tokens
        self.system_prompt_tokens = system_prompt_tokens
        self.model_name = model_name
        self.available_tokens = max_context_tokens - reserve_tokens - system_prompt_tokens

        self._history: List[ContextEntry] = []
        self._token_count = 0
        self._last_token_estimate = 0

    @property
    def total_tokens_used(self) -> int:
        """Total tokens used from the context window."""
        return self._token_count

    @property
    def tokens_remaining(self) -> int:
        """Tokens remaining in the context window."""
        return max(0, self.available_tokens - self._token_count)

    def add_user_turn(self, query: str) -> None:
        """Add a user turn to the context."""
        token_count = self._estimate_tokens(query)
        turn = ConversationTurn(
            role="user",
            content=query,
            timestamp=datetime.utcnow().isoformat(),
            token_count=token_count,
        )
        entry = ContextEntry(turn=turn, importance=1.0)
        self._history.append(entry)
        self._token_count += token_count

    def add_assistant_turn(self, response: str) -> None:
        """Add an assistant turn to the context."""
        token_count = self._estimate_tokens(response)
        turn = ConversationTurn(
            role="assistant",
            content=response,
            timestamp=datetime.utcnow().isoformat(),
            token_count=token_count,
        )
        entry = ContextEntry(turn=turn, importance=0.8)
        self._history.append(entry)
        self._token_count += token_count

    def add_tool_result(self, tool_name: str, result: Any, is_success: bool = True) -> None:
        """Add a tool result to the context."""
        summarized = ToolResult(
            tool_name=tool_name,
            result=result,
            timestamp=datetime.utcnow().isoformat(),
            token_count=0,  # Will be estimated
            is_success=is_success,
        )
        # Tool results are less important if successful
        importance = 0.3 if is_success else 0.9
        entry = ContextEntry(tool_result=summarized, importance=importance)
        self._history.append(entry)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        # Rough estimate: 4 chars ~= 1 token
        return max(1, len(text) // 4)

    def _update_token_estimates(self) -> None:
        """Update token estimates for all entries."""
        self._token_count = 0
        for entry in self._history:
            if entry.turn:
                entry.turn.token_count = self._estimate_tokens(entry.turn.content)
                self._token_count += entry.turn.token_count
            if entry.tool_result:
                entry.tool_result.token_count = self._estimate_tokens(
                    str(entry.tool_result.result)[:500]  # Limit for estimation
                )
                self._token_count += entry.tool_result.token_count

    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get the current message list for the API, respecting token budget.

        Returns a list of dicts with 'role' and 'content' keys, ordered from
        oldest to newest.
        """
        # Update token estimates
        self._update_token_estimates()

        if self._token_count <= self.available_tokens:
            # We have room for everything
            messages = []
            for entry in self._history:
                if entry.turn:
                    messages.append({"role": entry.turn.role, "content": entry.turn.content})
            return messages

        # Need to truncate - prioritize by importance and recency
        logger.debug(f"Context overflow: {self._token_count} > {self.available_tokens}")

        # Sort by importance (descending) and recency, keep most important
        indexed = [(i, entry) for i, entry in enumerate(self._history)]
        indexed.sort(key=lambda x: (x[1].importance, -x[0]), reverse=True)

        # How many entries can we fit?
        target_tokens = self.available_tokens
        selected_indices = []
        current_tokens = 0

        for idx, entry in indexed:
            entry_tokens = 0
            if entry.turn:
                entry_tokens += entry.turn.token_count
            if entry.tool_result:
                entry_tokens = entry.tool_result.token_count

            if current_tokens + entry_tokens <= target_tokens:
                selected_indices.append(idx)
                current_tokens += entry_tokens

        # Keep system prompt tokens for the first turn
        # Sort selected indices by original order
        selected_indices.sort()

        # Build messages, preserving order
        messages = []
        seen_indices = set(selected_indices)

        for i, entry in enumerate(self._history):
            if i in seen_indices:
                if entry.turn:
                    messages.append({"role": entry.turn.role, "content": entry.turn.content})
                elif entry.tool_result:
                    # Convert tool result to string message
                    content = entry.tool_result.summarized
                    messages.append({"role": "assistant", "content": f"Tool result: {content}"})

        return messages

    def get_compact_context(self) -> Dict[str, Any]:
        """Get a compact representation of the current context."""
        return {
            "token_count": self._token_count,
            "tokens_available": self.available_tokens,
            "tokens_remaining": self.tokens_remaining,
            "history_length": len(self._history),
            "model_name": self.model_name,
        }

    def should_warn_user(self) -> bool:
        """Check if we should warn the user about context limits."""
        return self.tokens_remaining < (self.available_tokens * 0.2)

    def get_summary(self) -> str:
        """Get a human-readable summary of the context state."""
        usage_pct = (self._token_count / self.available_tokens * 100) if self.available_tokens > 0 else 0
        warning = " (WARNING: context nearly full)" if self.should_warn_user() else ""
        return f"Context: {self._token_count}/{self.available_tokens} tokens ({usage_pct:.1f}%){warning}"

    def reset(self) -> None:
        """Reset the context history."""
        self._history = []
        self._token_count = 0

    def clear_tool_results(self, older_than_seconds: int = 300) -> None:
        """Clear tool results older than specified seconds to free up context."""
        cutoff = time.time() - older_than_seconds
        removed = 0
        for entry in self._history:
            if entry.tool_result:
                try:
                    ts = datetime.fromisoformat(entry.tool_result.timestamp).timestamp()
                    if ts < cutoff:
                        entry.tool_result = None
                        removed += 1
                except (ValueError, TypeError):
                    pass
        if removed > 0:
            self._update_token_estimates()
            logger.debug(f"Cleared {removed} old tool results from context")

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the full conversation history for storage."""
        return [entry.to_dict() for entry in self._history]

    def load_conversation_history(self, history: List[Dict[str, Any]]) -> None:
        """Load conversation history from storage."""
        self._history = [ContextEntry.from_dict(entry) for entry in history]
        self._update_token_estimates()

    def get_recent_turns(self, count: int = 5) -> List[ConversationTurn]:
        """Get the most recent conversation turns."""
        turns = [entry.turn for entry in self._history if entry.turn]
        return turns[-count:] if len(turns) >= count else turns

    def summarize_old_turns(self, max_turns: int = 10) -> None:
        """Summarize turns beyond max_turns to fit context budget."""
        if len(self._history) <= max_turns:
            return

        # Mark older turns for summarization
        for i, entry in enumerate(self._history):
            if i < len(self._history) - max_turns and entry.turn and entry.importance > 0.3:
                # Reduce importance to trigger summarization/truncation
                entry.importance = 0.1

        logger.debug(f"Marked old turns for summarization (total: {len(self._history)})")


def estimate_tokens(text: str) -> int:
    """Convenience function to estimate tokens in text."""
    if not text:
        return 0
    return max(1, len(text) // 4)