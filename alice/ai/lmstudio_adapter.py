#!/usr/bin/env python3
"""Real LM Studio adapter using its local REST and OpenAI-compatible APIs.

The adapter never sends prompts to a cloud provider. All requests target the
configured loopback server (127.0.0.1 by default).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, AsyncGenerator, Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .adapter import AIProvider
from .model_capability import create_model_detector, ModelCapabilityDetector

logger = logging.getLogger(__name__)


class LMStudioError(RuntimeError):
    """Raised when LM Studio is unavailable or returns an invalid response."""


class TruncatedResponseError(LMStudioError):
    """Raised when generation is truncated due to token limit."""
    def __init__(self, message: str, finish_reason: str, retry_count: int = 0):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.retry_count = retry_count


class LMStudioAdapter(AIProvider):
    """Connect ALICE to a local LM Studio server."""

    def __init__(self, config: Any):
        self.config = config
        ai = getattr(config, "ai", None)
        self.base_url = (getattr(ai, "base_url", None) or "http://127.0.0.1:1234").rstrip("/")
        self.api_token = getattr(ai, "api_token", "") or os.getenv("LM_API_TOKEN", "")
        self.request_timeout = int(getattr(ai, "request_timeout", 120) or 120)
        self.startup_timeout = int(getattr(ai, "startup_timeout", 25) or 25)
        self.auto_start_server = bool(getattr(ai, "auto_start_server", True))
        self.lms_cli = getattr(ai, "lms_cli", "") or ""
        self.runtime_running = False
        self.model_loaded = False
        self.current_model: Optional[str] = None
        self.current_instance_id: Optional[str] = None
        self.last_activity = time.time()
        self.last_error: Optional[str] = None
        self._model_cache: List[Dict[str, Any]] = []
        self._server_process: Optional[subprocess.Popen] = None
        self._started_server = False
        self._retry_count = 0

        # Initialize model capability detector for centralized arg normalization
        self._model_detector = create_model_detector(config)

        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"Invalid LM Studio base URL: {self.base_url}")
        if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            logger.warning("LM Studio endpoint is not loopback. Local-only mode is recommended.")

    def _validate_generation_budget(self) -> tuple[int, int]:
        """Validate and return (context_length, max_tokens) ensuring max_tokens fits in context."""
        ai = getattr(self.config, "ai", None)
        context_length = int(getattr(ai, "context_length", 8192))
        max_tokens = int(getattr(ai, "max_tokens", 3072))

        # Reserve tokens for prompt (at least 1024 tokens for system + user messages)
        reserved = 1024
        effective_max = min(max_tokens, max(0, context_length - reserved))

        if effective_max != max_tokens:
            logger.warning(
                "max_tokens (%d) exceeds available context budget (%d - %d = %d). "
                "Using %d instead.",
                max_tokens, context_length, reserved, context_length - reserved, effective_max
            )
        return context_length, effective_max

    def normalize_tool_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        force_xml: bool = False,
    ) -> Dict[str, Any]:
        """
        Centralized tool argument normalization and validation.

        Ensures all tool arguments are properly formatted before dispatch.
        Handles:
        - String vs dict argument normalization
        - Type validation
        - XML fallback for models that need it

        Args:
            tool_name: Name of the tool being called
            arguments: Raw arguments from the model
            force_xml: Force XML fallback mode even if native is available

        Returns:
            Normalized and validated arguments dict
        """
        # Check if model requires XML fallback
        if not force_xml and not self._model_detector.requires_xml_fallback():
            # Native tool calling - validate and ensure dict format
            normalized = {}
            for key, value in arguments.items():
                if isinstance(value, str):
                    # Try to parse as JSON dict if it looks like one
                    if value.startswith("{") and value.endswith("}"):
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, dict):
                                normalized[key] = parsed
                                continue
                        except json.JSONDecodeError:
                            pass
                    normalized[key] = value
                elif isinstance(value, (int, float, bool)):
                    normalized[key] = value
                elif isinstance(value, list):
                    normalized[key] = value
                elif isinstance(value, dict):
                    normalized[key] = value
                else:
                    normalized[key] = str(value)
            return normalized
        else:
            # XML fallback mode - ensure all args are strings for XML generation
            xml_args = {}
            for key, value in arguments.items():
                if isinstance(value, str):
                    xml_args[key] = value
                elif isinstance(value, (int, float, bool)):
                    xml_args[key] = str(value)
                elif isinstance(value, dict):
                    # Recursively normalize nested dicts
                    xml_args[key] = self._dict_to_xml_string(value)
                elif isinstance(value, list):
                    xml_args[key] = [self._dict_to_xml_string(item) if isinstance(item, dict) else str(item) for item in value]
                else:
                    xml_args[key] = str(value)
            return xml_args

    def _dict_to_xml_string(self, d: Dict[str, Any]) -> str:
        """Convert a dict to a simple XML string representation."""
        if not isinstance(d, dict):
            return str(d)
        parts = []
        for key, value in d.items():
            if isinstance(value, dict):
                parts.append(f"<{key}>{self._dict_to_xml_string(value)}</{key}>")
            elif isinstance(value, list):
                items = "".join(
                    f"<item>{self._dict_to_xml_string(i) if isinstance(i, dict) else str(i)}</item>"
                    for i in value
                )
                parts.append(f"<{key}>{items}</{key}>")
            else:
                parts.append(f"<{key}>{value}</{key}>")
        return "".join(parts)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _request(self, method: str, path: str, payload: Optional[dict] = None,
                 timeout: Optional[int] = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, headers=self._headers(), method=method.upper())
        try:
            with urlopen(request, timeout=timeout or self.request_timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise LMStudioError(f"LM Studio returned invalid JSON from {path}") from exc
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise LMStudioError(f"LM Studio HTTP {exc.code} for {path}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LMStudioError(f"Cannot reach LM Studio at {url}: {exc}") from exc

    def _find_lms(self) -> Optional[str]:
        if self.lms_cli:
            candidate = os.path.expandvars(os.path.expanduser(self.lms_cli))
            if os.path.isfile(candidate):
                return candidate
            found = shutil.which(candidate)
            if found:
                return found
        found = shutil.which("lms") or shutil.which("lms.exe")
        if found:
            return found
        local = os.getenv("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local, "Programs", "LM Studio", "resources", "app", ".webpack", "lms.exe"),
            os.path.join(local, "Programs", "LM Studio", "lms.exe"),
        ] if local else []
        return next((p for p in candidates if os.path.isfile(p)), None)

    def start_runtime(self) -> bool:
        """Connect to the local server, starting it with `lms` if configured."""
        try:
            self._request("GET", "/api/v1/models", timeout=3)
            self.runtime_running = True
            self.last_error = None
            return True
        except LMStudioError as initial_error:
            if not self.auto_start_server:
                self.last_error = str(initial_error)
                return False

        cli = self._find_lms()
        if not cli:
            self.last_error = (
                "LM Studio server is not running and the `lms` CLI was not found. "
                "Open LM Studio > Developer and turn on Start server, or install the LM Studio CLI."
            )
            logger.warning(self.last_error)
            return False

        try:
            command = [cli, "server", "start"]
            # The server uses port 1234 by default; add a port only when configured.
            parsed = urlparse(self.base_url)
            if parsed.port and parsed.port != 1234:
                command.extend(["--port", str(parsed.port)])
            self._server_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._started_server = True
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"Could not start LM Studio server using lms: {exc}"
            logger.exception(self.last_error)
            return False

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            try:
                self._request("GET", "/api/v1/models", timeout=2)
                self.runtime_running = True
                self.last_error = None
                return True
            except LMStudioError:
                time.sleep(0.5)

        self.last_error = "LM Studio CLI was invoked, but the local server did not become ready in time."
        logger.error(self.last_error)
        return False

    def stop_runtime(self) -> bool:
        """Disconnect ALICE; leave the LM Studio server running for other local apps."""
        try:
            self.unload_model()
        except Exception:
            logger.exception("Failed to unload model while stopping adapter")
        self.runtime_running = False
        # Deliberately do not kill the server: it may be shared by the user or
        # another local application. The model is unloaded separately.
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/v1/models")
        models = data.get("models", []) if isinstance(data, dict) else []
        normalized = []
        for item in models:
            if item.get("type") != "llm":
                continue
            loaded = item.get("loaded_instances") or []
            normalized.append({
                "id": item.get("key", ""),
                "name": item.get("display_name") or item.get("key", ""),
                "size_bytes": item.get("size_bytes"),
                "params": item.get("params_string"),
                "format": item.get("format"),
                "quantization": (item.get("quantization") or {}).get("name"),
                "loaded": bool(loaded),
                "loaded_instances": loaded,
                "supports_tool_calling": bool((item.get("capabilities") or {}).get("trained_for_tool_use", False)),
                "raw": item,
            })
        self._model_cache = normalized
        return normalized

    def _resolve_model(self, requested: str) -> Dict[str, Any]:
        models = self.list_models()
        if not models:
            raise LMStudioError("No installed LLM models were returned by LM Studio. Check that Qwen is downloaded.")
        query = (requested or "").strip().casefold()
        if query:
            exact = next((m for m in models if query in (m["id"].casefold(), m["name"].casefold())), None)
            if exact:
                return exact
            partial = [m for m in models if query in m["id"].casefold() or query in m["name"].casefold()]
            if len(partial) == 1:
                return partial[0]
        # Auto-select Qwen 3.5 4B when the config does not specify an ID.
        preferred = [m for m in models if "qwen" in (m["id"] + " " + m["name"]).casefold()
                     and ("3.5" in (m["id"] + " " + m["name"]).casefold() or "3_5" in (m["id"] + " " + m["name"]).casefold())
                     and "4b" in (m["id"] + " " + m["name"]).casefold()]
        if len(preferred) == 1:
            return preferred[0]
        if len(models) == 1:
            return models[0]
        choices = ", ".join(m["id"] for m in models[:8])
        raise LMStudioError(f"Could not uniquely identify model '{requested}'. Available models: {choices}")

    def load_model(self, model_name: str) -> bool:
        if not self.runtime_running and not self.start_runtime():
            return False
        try:
            model = self._resolve_model(model_name)
            if model.get("loaded_instances"):
                instance = model["loaded_instances"][0]
                self.current_model = model["id"]
                self.current_instance_id = instance.get("id") or model["id"]
                self.model_loaded = True
                self.last_activity = time.time()
                return True
            ai = getattr(self.config, "ai", None)
            context_length, _ = self._validate_generation_budget()
            payload = {
                "model": model["id"],
                "context_length": context_length,
                "echo_load_config": True,
            }
            data = self._request("POST", "/api/v1/models/load", payload)
            self.current_model = model["id"]
            self.current_instance_id = data.get("instance_id") or model["id"]
            self.model_loaded = data.get("status", "loaded") == "loaded"
            self.last_activity = time.time()
            self.last_error = None
            return self.model_loaded
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Failed to load LM Studio model")
            self.model_loaded = False
            self.current_model = None
            self.current_instance_id = None
            return False

    def unload_model(self) -> bool:
        if not self.model_loaded or not self.current_instance_id:
            self.model_loaded = False
            self.current_model = None
            self.current_instance_id = None
            return True
        try:
            self._request("POST", "/api/v1/models/unload", {"instance_id": self.current_instance_id})
            self.model_loaded = False
            self.current_model = None
            self.current_instance_id = None
            self.last_activity = time.time()
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Failed to unload LM Studio model")
            return False

    def _completion_payload(self, messages: List[Dict[str, Any]], **kwargs) -> dict:
        if not self.model_loaded or not self.current_model:
            raise LMStudioError("No model is loaded. Call load_model() first.")
        ai = getattr(self.config, "ai", None)
        _, effective_max_tokens = self._validate_generation_budget()
        payload = {
            "model": self.current_model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", getattr(ai, "temperature", 0.7)),
            "max_tokens": kwargs.pop("max_tokens", effective_max_tokens),
        }
        for key in ("tools", "tool_choice", "response_format", "stop", "top_p", "seed"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs.pop(key)
        payload.update(kwargs)
        return payload

    def _parse_response(self, data: dict, retry_count: int = 0) -> tuple[str, dict]:
        """Parse LM Studio response, extracting content and metadata.

        Returns:
            tuple: (content, metadata_dict) where metadata contains diagnostic info
        """
        choices = data.get("choices") or []
        if not choices:
            raise LMStudioError(f"LM Studio returned no choices: {data}")
        choice = choices[0] or {}
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason", "unknown")

        # Extract diagnostic fields
        reasoning_content = message.get("reasoning_content")
        tool_calls = message.get("tool_calls")
        content = message.get("content")

        # Diagnostics logging
        content_length = len(content) if isinstance(content, str) else 0
        has_reasoning = reasoning_content is not None
        tool_call_count = len(tool_calls) if isinstance(tool_calls, list) else 0

        logger.info(
            "LM Studio response: model=%s context_len=%d max_tokens=%d "
            "finish_reason=%s content_len=%d has_reasoning=%s tool_calls=%d retry=%d",
            self.current_model,
            *self._validate_generation_budget(),
            finish_reason,
            content_length,
            has_reasoning,
            tool_call_count,
            retry_count
        )

        # Handle tool calls - preserve native format for ALICE's tool execution system
        if tool_calls:
            # Normalize tool_calls using centralized argument normalization
            normalized_tool_calls = []
            for tc in tool_calls:
                if isinstance(tc, dict) and "function" in tc:
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    # Use centralized normalization
                    normalized_args = self.normalize_tool_arguments(
                        func.get("name", ""),
                        args if isinstance(args, dict) else {}
                    )
                    if isinstance(normalized_args, str):
                        # If normalization returned a string (XML fallback), use as-is
                        normalized_args_str = normalized_args
                    else:
                        # Otherwise, serialize back to JSON string
                        normalized_args_str = json.dumps(normalized_args, ensure_ascii=False)
                    normalized_tc = {
                        "id": tc.get("id"),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": func.get("name"),
                            "arguments": normalized_args_str
                        }
                    }
                    normalized_tool_calls.append(normalized_tc)
                else:
                    normalized_tool_calls.append(tc)

            # Return content and tool_calls as JSON string for ALICE to handle
            result = {
                "content": content if content else None,
                "tool_calls": normalized_tool_calls,
                "has_tool_calls": True
            }
            return json.dumps(result, ensure_ascii=False), {
                "finish_reason": finish_reason,
                "has_reasoning": has_reasoning,
                "tool_call_count": tool_call_count,
            }

        # Handle content blocks (OpenAI-compatible format)
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            content = "\n".join(part for part in parts if part.strip())

        # Handle empty content
        if not isinstance(content, str) or not content.strip():
            refusal = message.get("refusal")
            if isinstance(refusal, str) and refusal.strip():
                raise LMStudioError(f"The model refused the request: {refusal.strip()}")

            # Check for truncated response
            if finish_reason == "length":
                if retry_count == 0:
                    # Trigger retry with concise instruction
                    raise TruncatedResponseError(
                        "Generation truncated: finish_reason='length'",
                        finish_reason=finish_reason,
                        retry_count=retry_count
                    )
                else:
                    # Retry also failed
                    raise TruncatedResponseError(
                        "Generation truncated after retry. Try a shorter prompt or increase context length.",
                        finish_reason=finish_reason,
                        retry_count=retry_count
                    )

            detail = (
                "LM Studio returned an empty user-facing answer. "
                f"finish_reason={finish_reason!r}; response fields={sorted(message.keys())}. "
                "Check the LM Studio model load/context settings and try a short prompt."
            )
            self.last_error = detail
            raise LMStudioError(detail)

        # Handle truncated response with non-empty content
        # If finish_reason is "length", the generation was cut off
        if finish_reason == "length":
            if retry_count == 0:
                # Trigger retry with concise instruction
                raise TruncatedResponseError(
                    "Generation truncated: finish_reason='length'",
                    finish_reason=finish_reason,
                    retry_count=retry_count
                )
            else:
                # Retry also failed - raise error
                raise TruncatedResponseError(
                    "Generation truncated after retry. Try a shorter prompt or increase context length.",
                    finish_reason=finish_reason,
                    retry_count=retry_count
                )

        return content.strip(), {
            "finish_reason": finish_reason,
            "has_reasoning": has_reasoning,
            "tool_call_count": tool_call_count,
        }

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Reset retry count for new conversation
        self._retry_count = 0

        while True:
            payload = self._completion_payload(messages, **kwargs)
            data = self._request("POST", "/v1/chat/completions", payload)

            try:
                content, _ = self._parse_response(data, retry_count=self._retry_count)
                return content
            except TruncatedResponseError as e:
                if self._retry_count >= 1:
                    # Already retried once, give up
                    raise LMStudioError(str(e)) from e

                # Retry once with concise instruction and reduced token budget
                self._retry_count += 1
                logger.warning(
                    "Generation truncated (finish_reason=length), retrying with concise instruction. "
                    "Attempt %d/1", self._retry_count
                )

                # Add concise instruction to the last user message
                retry_messages = [dict(m) for m in messages]
                if retry_messages and retry_messages[-1].get("role") == "user":
                    retry_messages[-1]["content"] = (
                        retry_messages[-1]["content"] +
                        "\n\n[System: Provide a concise answer. Keep it brief.]"
                    )

                # Reduce max_tokens for retry
                kwargs["max_tokens"] = min(
                    kwargs.get("max_tokens", 1024),
                    1024  # Cap at 1024 for concise retry
                )
                messages = retry_messages
                continue

    def _iter_stream(self, payload: dict) -> Iterator[str]:
        payload = dict(payload)
        payload["stream"] = True
        body = json.dumps(payload).encode("utf-8")
        request = Request(f"{self.base_url}/v1/chat/completions", data=body,
                          headers={**self._headers(), "Accept": "text/event-stream"}, method="POST")
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content
            self.last_activity = time.time()
            self.last_error = None
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self.last_error = str(exc)
            raise LMStudioError(f"LM Studio streaming request failed: {exc}") from exc

    async def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        payload = self._completion_payload(messages, **kwargs)
        iterator = iter(self._iter_stream(payload))
        sentinel = object()
        while True:
            def next_item():
                try:
                    return next(iterator)
                except StopIteration:
                    return sentinel
            item = await asyncio.to_thread(next_item)
            if item is sentinel:
                break
            yield item

    def supports_tool_calling(self) -> bool:
        if not self.current_model:
            return False
        try:
            model = next((m for m in self.list_models() if m["id"] == self.current_model), None)
            return bool(model and model["supports_tool_calling"])
        except LMStudioError:
            return False

    def get_runtime_status(self) -> Dict[str, Any]:
        reachable = False
        try:
            self.list_models()
            reachable = True
        except LMStudioError as exc:
            self.last_error = str(exc)
        self.runtime_running = reachable
        return {
            "runtime": "lmstudio",
            "base_url": self.base_url,
            "runtime_running": reachable,
            "model_loaded": self.model_loaded,
            "current_model": self.current_model,
            "idle_time": max(0.0, time.time() - self.last_activity),
            "last_error": self.last_error,
        }

    def health_check(self) -> Dict[str, str]:
        try:
            models = self.list_models()
            loaded = any(m.get("loaded") for m in models)
            return {
                "runtime": "ok",
                "api": "ok",
                "model": "loaded" if loaded else "not loaded",
                "installed_models": str(len(models)),
            }
        except LMStudioError as exc:
            self.last_error = str(exc)
            return {"runtime": "unavailable", "api": "unavailable", "model": "unknown", "error": str(exc)}

    def check_idle_timeout(self) -> bool:
        if not self.model_loaded or not self.config:
            return False
        idle_timeout = int(getattr(self.config.ai, "idle_timeout", 300))
        return (time.time() - self.last_activity) > idle_timeout
