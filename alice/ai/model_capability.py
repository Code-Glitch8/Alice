#!/usr/bin/env python3
"""
Model Capability Detection for ALICE.

Detects and caches model capabilities for adaptive behavior.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Callable

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a model."""
    id: str
    name: str = ""
    description: str = ""
    version: str = ""
    context_length: int = 4096
    supports_tools_native: bool = False
    supports_reasoning: bool = False
    supports_system_prompt: bool = True
    supports_fim: bool = False
    alias: str = ""
    created: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "context_length": self.context_length,
            "supports_tools_native": self.supports_tools_native,
            "supports_reasoning": self.supports_reasoning,
            "supports_system_prompt": self.supports_system_prompt,
            "supports_fim": self.supports_fim,
            "alias": self.alias,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelInfo":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", ""),
            context_length=data.get("context_length", 4096),
            supports_tools_native=data.get("supports_tools_native", False),
            supports_reasoning=data.get("supports_reasoning", False),
            supports_system_prompt=data.get("supports_system_prompt", True),
            supports_fim=data.get("supports_fim", False),
            alias=data.get("alias", ""),
            created=data.get("created", 0),
        )


@dataclass
class DetectionResult:
    """Result of capability detection."""
    is_determined: bool = False
    model_info: Optional[ModelInfo] = None
    confidence: float = 0.0
    test_results: Dict[str, bool] = field(default_factory=dict)
    notes: str = ""
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_determined": self.is_determined,
            "model_info": self.model_info.to_dict() if self.model_info else None,
            "confidence": self.confidence,
            "test_results": self.test_results,
            "notes": self.notes,
            "detected_at": self.detected_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectionResult":
        return cls(
            is_determined=data.get("is_determined", False),
            model_info=ModelInfo.from_dict(data["model_info"]) if data.get("model_info") else None,
            confidence=data.get("confidence", 0.0),
            test_results=data.get("test_results", {}),
            notes=data.get("notes", ""),
            detected_at=data.get("detected_at", datetime.utcnow().isoformat()),
        )


class ModelCapabilityDetector:
    """
    Detects and caches model capabilities for adaptive ALICE behavior.

    This class probes the model endpoint to determine:
    - Whether native tool calling is supported
    - Context window size
    - Model family and version
    - Other capabilities
    """

    # Known model patterns and their capabilities
    MODEL_CAPABILITIES = {
        # Qwen models
        "qwen": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 32768,
            "xml_fallback_needed": False,
        },
        "qwen2.5": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 32768,
            "xml_fallback_needed": False,
        },
        "qwen3": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 32768,
            "xml_fallback_needed": False,
        },
        # OpenAI models (if running via compatible endpoint)
        "gpt-4": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 8192,
            "xml_fallback_needed": False,
        },
        "gpt-4o": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 128000,
            "xml_fallback_needed": False,
        },
        "gpt-4.5": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 128000,
            "xml_fallback_needed": False,
        },
        "gpt-3.5-turbo": {
            "supports_tools_native": True,
            "supports_reasoning": False,
            "context_length": 16385,
            "xml_fallback_needed": False,
        },
        # Claude models
        "claude": {
            "supports_tools_native": True,
            "supports_reasoning": True,
            "context_length": 200000,
            "xml_fallback_needed": False,
        },
        "claude-opus": {
            "supports_tools_native": True,
            "supports_reasoning": True,
            "context_length": 200000,
            "xml_fallback_needed": False,
        },
        "claude-sonnet": {
            "supports_tools_native": True,
            "supports_reasoning": True,
            "context_length": 200000,
            "xml_fallback_needed": False,
        },
        "claude-haiku": {
            "supports_tools_native": True,
            "supports_reasoning": True,
            "context_length": 200000,
            "xml_fallback_needed": False,
        },
    }

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        api_token: str = "",
        request_timeout: int = 30,
    ):
        """
        Initialize the Model Capability Detector.

        Args:
            base_url: URL of the model server
            api_token: API token if required
            request_timeout: Timeout for HTTP requests
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.request_timeout = request_timeout
        self._cached_result: Optional[DetectionResult] = None
        self._cache_time: float = 0
        self._cache_ttl: int = 3600  # 1 hour cache

    @property
    def cached(self) -> bool:
        """Check if we have a valid cached result."""
        if not self._cached_result:
            return False
        return time.time() - self._cache_time < self._cache_ttl

    def get_cache_key(self) -> str:
        """Get a cache key for the current configuration."""
        return f"{self.base_url}:{self.api_token[:8] if self.api_token else 'none'}"

    async def detect_capabilities(
        self,
        force_refresh: bool = False,
    ) -> DetectionResult:
        """
        Detect model capabilities.

        This is an async method to support HTTP requests.
        For sync usage, use detect_capabilities_sync().

        Args:
            force_refresh: Force detection even if cached

        Returns:
            DetectionResult with model info and capabilities
        """
        if not force_refresh and self.cached:
            return self._cached_result

        try:
            # Get models list
            models = await self._list_models()

            # Find the best matching model
            model_info = self._identify_model(models)

            if not model_info:
                # Unknown model, use conservative defaults
                model_info = ModelInfo(
                    id="unknown",
                    context_length=8192,
                    supports_tools_native=False,
                    notes="Unknown model, using conservative defaults",
                )

            # Test native tool calling
            supports_native = await self._test_native_tool_calling(model_info)

            model_info.supports_tools_native = supports_native

            result = DetectionResult(
                is_determined=True,
                model_info=model_info,
                confidence=0.9 if supports_native else 0.6,
                test_results={"native_tool_calling": supports_native},
                notes="Capabilities determined from model metadata and testing",
            )

            self._cached_result = result
            self._cache_time = time.time()

            return result

        except Exception as e:
            logger.warning(f"Capability detection failed: {e}")
            return DetectionResult(
                is_determined=False,
                is_determined_reason=str(e),
                confidence=0.0,
                notes=f"Detection failed: {e}",
            )

    def detect_capabilities_sync(self, force_refresh: bool = False) -> DetectionResult:
        """
        Synchronous version of detect_capabilities.

        Args:
            force_refresh: Force detection even if cached

        Returns:
            DetectionResult with model info and capabilities
        """
        if not force_refresh and self.cached:
            return self._cached_result

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, need to use async method
                return asyncio.ensure_future(self.detect_capabilities(force_refresh))
            except RuntimeError:
                # No running loop, create one
                return asyncio.run(self.detect_capabilities(force_refresh))
        except Exception as e:
            logger.warning(f"Capability detection failed: {e}")
            return DetectionResult(
                is_determined=False,
                confidence=0.0,
                notes=f"Detection failed: {e}",
            )

    async def _list_models(self) -> List[Dict[str, Any]]:
        """List available models from the server."""
        import httpx

        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
        except Exception as e:
            logger.debug(f"Could not list models: {e}")
            return []

    def _identify_model(self, models: List[Dict[str, Any]]) -> Optional[ModelInfo]:
        """Identify the model from the list, matching by known patterns."""
        if not models:
            return None

        # Try to find a model matching our expected name
        for model in models:
            model_id = model.get("id", "").lower()
            model_name = model.get("name", "").lower()

            # Check for Qwen3.5-4B pattern
            if "qwen" in model_id or "qwen" in model_name:
                info = ModelInfo(
                    id=model.get("id", ""),
                    name=model.get("name", ""),
                    alias="qwen3.5-4b" if "3.5" in model_id or "3.5" in model_name else "qwen",
                    context_length=8192,  # Default for Qwen
                    supports_tools_native=True,  # Qwen supports native tools
                )
                return info

            # Check for Qwen3 explicit
            if "qwen3" in model_id:
                return ModelInfo(
                    id=model.get("id", ""),
                    name=model.get("name", ""),
                    context_length=32768,
                    supports_tools_native=True,
                )

            # Check for Qwen2
            if "qwen2" in model_id:
                return ModelInfo(
                    id=model.get("id", ""),
                    name=model.get("name", ""),
                    context_length=32768,
                    supports_tools_native=True,
                )

        # Return first model if found
        if models:
            model = models[0]
            model_id = model.get("id", "").lower()

            # Match against known patterns
            context_len = 8192
            supports_native = True
            prefix = ""

            for pattern, caps in self.MODEL_CAPABILITIES.items():
                if pattern in model_id:
                    prefix = pattern
                    context_len = caps.get("context_length", 8192)
                    supports_native = caps.get("supports_tools_native", True)
                    break

            return ModelInfo(
                id=model.get("id", ""),
                name=model.get("name", ""),
                context_length=context_len,
                supports_tools_native=supports_native,
                created=model.get("created", 0),
            )

        return None

    async def _test_native_tool_calling(self, model_info: ModelInfo) -> bool:
        """
        Test if the model can handle native tool calling.

        Uses a simple test completion with a tool call attempt.
        """
        import httpx

        # If we already know from metadata
        if model_info.supports_tools_native is not None:
            # Use known capabilities for known models
            model_id = (model_info.id or "").lower()
            for pattern, caps in self.MODEL_CAPABILITIES.items():
                if pattern in model_id and caps.get("supports_tools_native"):
                    return True

        # Test with a simple tool call
        test_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool to verify native tool calling",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        ]

        messages = [{"role": "user", "content": "Test tool calling capability. Call test_tool if tool calling works."}]

        headers = {
            "Authorization": f"Bearer {self.api_token}" if self.api_token else "",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_info.id or "default",
            "messages": messages,
            "tools": test_tools,
            "temperature": 0.0,
            "max_tokens": 10,
        }

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Check if tool calls were returned
                choices = data.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    tool_calls = message.get("tool_calls", [])
                    return len(tool_calls) > 0

        except Exception as e:
            logger.debug(f"Native tool calling test failed: {e}")

        return False

    def get_tool_call_mode(self) -> str:
        """
        Get the recommended tool call mode based on detected capabilities.

        Returns:
            "native" for native tool calling
            "xml" for XML fallback parsing
            "json" for strict JSON fallback
        """
        if not self._cached_result or not self._cached_result.model_info:
            # Conservative default if not detected
            model_id = ""
            try:
                import os
                model_id = os.getenv("LLM_MODEL_NAME", "").lower()
            except Exception:
                pass

            # Check for Qwen models that need XML fallback
            if "qwen" in model_id:
                return "xml"
            return "native"

        if self._cached_result.model_info.supports_tools_native:
            return "native"

        # Check model type for fallback mode
        model_id = (self._cached_result.model_info.id or "").lower()
        if "qwen" in model_id:
            return "xml"

        return "json"

    def supports_native_tool_calling(self) -> bool:
        """Check if the current model supports native tool calling."""
        if not self._cached_result:
            return False
        return self._cached_result.model_info.supports_tools_native

    def get_context_length(self) -> int:
        """Get the context length for the current model."""
        if not self._cached_result or not self._cached_result.model_info:
            return 8192
        return self._cached_result.model_info.context_length

    def requires_xml_fallback(self) -> bool:
        """Check if the model requires XML fallback parsing."""
        if not self._cached_result or not self._cached_result.model_info:
            return False

        # Check known models first
        model_id = (self._cached_result.model_info.id or "").lower()
        for pattern, caps in self.MODEL_CAPABILITIES.items():
            if pattern in model_id:
                return not caps.get("supports_tools_native", False)

        return not self._cached_result.model_info.supports_tools_native

    def get_recommended_context_tokens(self) -> int:
        """Get recommended context tokens for the current model."""
        context_len = self.get_context_length()
        # Reserve 20% for responses
        return int(context_len * 0.8)

    def clear_cache(self) -> None:
        """Clear the cached detection result."""
        self._cached_result = None
        self._cache_time = 0

    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache state."""
        return {
            "cached": self.cached,
            "cache_age": time.time() - self._cache_time if self._cache_time else None,
            "cache_ttl": self._cache_ttl,
        }


def create_model_detector(config: Any) -> ModelCapabilityDetector:
    """Factory function to create a detector from config."""
    ai_config = config.ai if hasattr(config, "ai") else config

    return ModelCapabilityDetector(
        base_url=getattr(ai_config, "base_url", "http://127.0.0.1:1234"),
        api_token=getattr(ai_config, "api_token", ""),
        request_timeout=getattr(ai_config, "request_timeout", 30),
    )