#!/usr/bin/env python3
"""
AI Runtime Adapter - Abstract base for local model providers.
Defines the common interface for LM Studio, Ollama, llama.cpp, etc.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator


class AIProvider(ABC):
    """Abstract base class for AI runtime adapters."""

    @abstractmethod
    def start_runtime(self) -> bool:
        """Start the AI runtime service."""
        pass

    @abstractmethod
    def stop_runtime(self) -> bool:
        """Stop the AI runtime service."""
        pass

    @abstractmethod
    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        pass

    @abstractmethod
    def load_model(self, model_name: str) -> bool:
        """Load a specific model."""
        pass

    @abstractmethod
    def unload_model(self) -> bool:
        """Unload the currently loaded model."""
        pass

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Send a chat message and get a response."""
        pass

    @abstractmethod
    def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        """Send a chat message and stream the response."""
        pass

    @abstractmethod
    def supports_tool_calling(self) -> bool:
        """Check if the model supports tool/function calling."""
        pass

    @abstractmethod
    def get_runtime_status(self) -> Dict[str, Any]:
        """Get current runtime status."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, str]:
        """Perform a health check on the runtime."""
        pass