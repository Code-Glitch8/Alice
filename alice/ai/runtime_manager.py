#!/usr/bin/env python3
"""Async lifecycle manager for ALICE's synchronous local-runtime adapter."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)


class RuntimeManager:
    def __init__(self, adapter: Any, config: Any):
        self.adapter = adapter
        self.config = config
        self.runtime_running = False
        self.model_loaded = False
        self.current_model: Optional[str] = None
        self.last_activity = time.time()
        self.idle_timeout = int(config.ai.idle_timeout)
        self._shutdown_event = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task] = None
        self._operation_lock = asyncio.Lock()

    async def start(self) -> bool:
        if self.runtime_running:
            return True
        logger.info("Starting ALICE runtime manager")
        ok = await asyncio.to_thread(self.adapter.start_runtime)
        self.runtime_running = bool(ok)
        if not ok:
            return False
        self._shutdown_event.clear()
        if self.config.ai.auto_load:
            await self.load_model()
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_idle(), name="alice-idle-monitor")
        return True

    async def stop(self) -> bool:
        self._shutdown_event.set()
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        async with self._operation_lock:
            await asyncio.to_thread(self.adapter.unload_model)
            ok = await asyncio.to_thread(self.adapter.stop_runtime)
            self.model_loaded = False
            self.current_model = None
            self.runtime_running = False
        return bool(ok)

    async def load_model(self, model_name: Optional[str] = None) -> bool:
        async with self._operation_lock:
            if self.model_loaded and (not model_name or model_name == self.current_model):
                return True
            if not self.runtime_running:
                started = await asyncio.to_thread(self.adapter.start_runtime)
                if not started:
                    return False
                self.runtime_running = True
            requested = model_name or self.config.ai.model_name
            ok = await asyncio.to_thread(self.adapter.load_model, requested)
            if ok:
                self.model_loaded = True
                self.current_model = getattr(self.adapter, "current_model", None) or requested
                self.last_activity = time.time()
            else:
                self.model_loaded = False
                self.current_model = None
            return bool(ok)

    async def unload_model(self) -> bool:
        async with self._operation_lock:
            ok = await asyncio.to_thread(self.adapter.unload_model)
            if ok:
                self.model_loaded = False
                self.current_model = None
                self.last_activity = time.time()
            return bool(ok)

    async def chat(self, messages: list, **kwargs) -> str:
        if not self.model_loaded and not await self.load_model():
            error = getattr(self.adapter, "last_error", None) or "Could not load the configured local model."
            raise RuntimeError(error)
        self.last_activity = time.time()
        result = await asyncio.to_thread(self.adapter.chat, messages, **kwargs)
        self.last_activity = time.time()
        return result

    async def stream_chat(self, messages: list, **kwargs) -> AsyncGenerator[str, None]:
        if not self.model_loaded and not await self.load_model():
            error = getattr(self.adapter, "last_error", None) or "Could not load the configured local model."
            raise RuntimeError(error)
        self.last_activity = time.time()
        async for token in self.adapter.stream_chat(messages, **kwargs):
            self.last_activity = time.time()
            yield token

    async def _monitor_idle(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(5)
                if self.model_loaded and (time.time() - self.last_activity) > self.idle_timeout:
                    logger.info("Model idle timeout reached; unloading model")
                    await self.unload_model()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Idle monitor error")

    def check_idle_timeout(self) -> bool:
        return self.model_loaded and (time.time() - self.last_activity) > self.idle_timeout

    def get_status(self) -> Dict[str, Any]:
        adapter_status = self.adapter.get_runtime_status()
        return {
            **adapter_status,
            "runtime_running": self.runtime_running or adapter_status.get("runtime_running", False),
            "model_loaded": self.model_loaded or adapter_status.get("model_loaded", False),
            "current_model": self.current_model or adapter_status.get("current_model"),
            "idle_time": max(0.0, time.time() - self.last_activity),
            "idle_timeout": self.idle_timeout,
            "config": {
                "context_length": self.config.ai.context_length,
                "temperature": self.config.ai.temperature,
                "max_tokens": self.config.ai.max_tokens,
            },
        }

    def health_check(self) -> Dict[str, str]:
        return self.adapter.health_check()
