"""Background asyncio runtime bridge for the PySide6 desktop dashboard."""
from __future__ import annotations

import asyncio
import threading
from typing import Any

from PySide6.QtCore import QThread, Signal

from alice.core.application import AliceApplication


class RuntimeWorker(QThread):
    """Own ALICE's asyncio runtime on a dedicated thread.

    Qt widgets never block while LM Studio is loading or tools are executing.
    """

    ready = Signal(bool, str)
    response = Signal(str)
    error = Signal(str)
    state_changed = Signal(str)
    hotkey_activated = Signal()
    wake_word_paused = Signal()
    confirmation_requested = Signal(str, object)

    def __init__(self, config: Any, parent=None):
        super().__init__(parent)
        self.config = config
        self.loop: asyncio.AbstractEventLoop | None = None
        self.runtime: AliceApplication | None = None
        self.history: list[dict[str, str]] = []
        self._stopping = False
        self.wake_detector = None
        self.wake_word_enabled = bool(
            getattr(config.voice, "wake_word_enabled", False)
            and not getattr(config.voice, "mute", False)
        )

    def run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.runtime = AliceApplication(self.config)
            self.runtime.permission_confirmation_callback = self._confirm_category_b
            self.runtime.event_bus.subscribe(
                "OMEN_KEY_PRESSED", lambda _event: self.hotkey_activated.emit()
            )
            try:
                connected = self.loop.run_until_complete(self.runtime.initialize())
                detail = (
                    "Connected to LM Studio. The model loads when you send the first message."
                    if connected
                    else (self.runtime.ai_adapter.last_error or "LM Studio is not available.")
                )
                self.ready.emit(bool(connected), detail)
                self.state_changed.emit("Connected" if connected else "Offline")
            except Exception as exc:
                self.ready.emit(False, str(exc))
                self.state_changed.emit("Offline")

            if self.wake_word_enabled:
                try:
                    from alice.voice.wake_word import WakeWordDetector
                    self.wake_detector = WakeWordDetector(self.config)
                    self.wake_detector.set_callback(self._on_wake_word_detected)
                    self.wake_detector.start()
                except Exception as exc:
                    self.error.emit(f"Wake-word monitor could not start: {exc}")

            self.loop.run_forever()
        finally:
            if self.wake_detector is not None:
                try:
                    self.loop.run_until_complete(self.wake_detector.stop_async())
                except Exception as exc:
                    self.error.emit(f"Wake-word shutdown warning: {exc}")
            if self.runtime is not None:
                try:
                    self.loop.run_until_complete(self.runtime.shutdown_async())
                except Exception as exc:
                    self.error.emit(f"Shutdown warning: {exc}")
            self.loop.close()
            self.loop = None
            self.state_changed.emit("Stopped")

    def send_message(self, message: str) -> None:
        text = message.strip()
        if not text or not self.loop or not self.loop.is_running() or self._stopping:
            self.error.emit("ALICE is still starting or is shutting down. Please try again.")
            return
        asyncio.run_coroutine_threadsafe(self._send_message(text), self.loop)

    async def _send_message(self, message: str) -> None:
        if self.runtime is None:
            self.error.emit("The ALICE runtime did not initialize.")
            return
        self.state_changed.emit("Thinking")
        self.history.append({"role": "user", "content": message})
        try:
            if not self.runtime.initialized:
                # initialize() already starts the hotkey/orb services on first launch.
                # Retry only the LM Studio runtime here to avoid registering duplicate hooks.
                if not await self.runtime.runtime.start():
                    raise RuntimeError(
                        self.runtime.ai_adapter.last_error or "Could not connect to LM Studio."
                    )
                self.runtime.initialized = True
                self.runtime.running = True
            # load_model is idempotent when the configured model is already loaded.
            if not await self.runtime.runtime.load_model():
                raise RuntimeError(
                    self.runtime.ai_adapter.last_error or "Could not load the configured model."
                )
            answer = await self.runtime.chat_with_tools(self.history)
            answer = (answer or "").strip()
            if not answer:
                answer = "The model returned an empty response. Please try again."
            self.history.append({"role": "assistant", "content": answer})
            self.response.emit(answer)
            self.state_changed.emit("Connected")
        except Exception as exc:
            self.history.pop()
            self.error.emit(str(exc))
            self.state_changed.emit("Error")

    def _on_wake_word_detected(self) -> None:
        self.hotkey_activated.emit()

    def pause_wake_word(self) -> None:
        if not self.loop or not self.loop.is_running():
            self.wake_word_paused.emit()
            return
        asyncio.run_coroutine_threadsafe(self._pause_wake_word(), self.loop)

    async def _pause_wake_word(self) -> None:
        if self.wake_detector is not None:
            await self.wake_detector.stop_async()
        self.wake_word_paused.emit()

    def resume_wake_word(self) -> None:
        if not self.wake_word_enabled or self._stopping:
            return
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._resume_wake_word(), self.loop)

    async def _resume_wake_word(self) -> None:
        if self.wake_detector is not None and not self.wake_detector.listening:
            try:
                await self.wake_detector.start_async()
            except Exception as exc:
                self.error.emit(f"Wake-word monitor could not resume: {exc}")

    async def _confirm_category_b(
        self, tool_name: str, description: str
    ) -> bool:
        """Request a user decision on the GUI thread; timeout means deny."""
        payload = {"event": threading.Event(), "approved": False}
        self.confirmation_requested.emit(
            f"ALICE wants to perform: {description} (tool: {tool_name}). Allow?",
            payload,
        )
        completed = await asyncio.to_thread(payload["event"].wait, 120)
        return bool(completed and payload["approved"])

    def stop(self) -> None:
        self._stopping = True
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.wait(15000)
