"""UI controller: connects REAL ALICE events to the Orb, and the Orb to ALICE.

It owns no AI runtime, no microphone pipeline and no TTS model.  It is handed
the dashboard's existing ``VoicePipeline`` and ``RuntimeWorker`` and only
translates their signals into visual state (and Orb clicks into calls on the
dashboard's existing voice workflow).  All Qt updates happen on the GUI
thread: background threads only emit Qt signals.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from alice.dashboard.model_lifecycle import ModelLifecycle, PowerState
from alice.dashboard.orb_state import OrbState, resolve_state

logger = logging.getLogger(__name__)


class UIController(QObject):
    power_changed = Signal(object, str)      # (PowerState, detail) - safe from any thread
    state_changed = Signal(object)           # OrbState for chips/orb

    SUCCESS_MS = 1400
    ERROR_MS = 4000

    def __init__(self, dashboard: Any, orb: Any, runtime_worker: Any, voice_pipeline: Any,
                 config: Any, lifecycle: Optional[ModelLifecycle] = None, parent=None):
        super().__init__(parent)
        self.dashboard = dashboard
        self.orb = orb
        self.worker = runtime_worker
        self.pipeline = voice_pipeline          # the dashboard's single VoicePipeline
        self.config = config
        self.lifecycle = lifecycle
        self.power = PowerState.OFF
        self.power_detail = ""
        self.listening = False
        self.thinking = False                    # runtime request or transcription in flight
        self.speaking = False
        self.transient: Optional[OrbState] = None
        self.powered_off = False                 # explicit Power Off: ignore hotkey/wake activation
        self._busy_thread: Optional[threading.Thread] = None
        self._idle = threading.Event(); self._idle.set()
        self._transient_timer = QTimer(self, singleShot=True)
        self._transient_timer.timeout.connect(self._clear_transient)
        self._level_timer = QTimer(self); self._level_timer.setInterval(50)
        self._level_timer.timeout.connect(self._poll_audio_level)
        self.power_changed.connect(self._on_power)

        if self.orb is not None:
            self.orb.toggle_voice.connect(self.dashboard.toggle_voice)
            self.orb.start_requested.connect(self.start_alice)
            self.orb.open_dashboard.connect(self.dashboard.show_dashboard)
            self.orb.action_requested.connect(self.handle_action)
        d = self.dashboard
        d.voice_recording_changed.connect(self._on_listening)
        d.transcribing_changed.connect(self._on_transcribing)
        d.speaking_changed.connect(self._on_speaking)
        d.shutdown_command.connect(self.shutdown_by_voice)
        d.power_action.connect(self.handle_action)
        d.voice_gate = lambda: not self.powered_off
        if self.worker is not None:
            self.worker.state_changed.connect(self._on_worker_state)
            self.worker.response.connect(self._on_response)
            self.worker.error.connect(self._on_error)
            self.worker.ready.connect(self._on_runtime_ready)
        self._refresh_visuals()

    # ---- lifecycle wiring ----------------------------------------------
    def _make_lifecycle(self) -> Optional[ModelLifecycle]:
        if self.lifecycle is not None:
            return self.lifecycle
        runtime = getattr(self.worker, "runtime", None)
        adapter = getattr(runtime, "ai_adapter", None)
        if adapter is None:
            return None
        self.lifecycle = ModelLifecycle(adapter, self.config, on_state=self.power_changed.emit)
        self.lifecycle.stop_listening = self._stop_listening_safely
        self.lifecycle.stop_speaking = self.pipeline.stop_speaking
        self.lifecycle.cancel_active_request = lambda: self._idle.wait(30)
        return self.lifecycle

    def attach_lifecycle(self, lifecycle: ModelLifecycle) -> None:
        self.lifecycle = lifecycle
        lifecycle._on_state = self.power_changed.emit
        lifecycle.stop_listening = self._stop_listening_safely
        lifecycle.stop_speaking = self.pipeline.stop_speaking
        lifecycle.cancel_active_request = lambda: self._idle.wait(30)

    def _stop_listening_safely(self) -> None:
        try:
            self.pipeline.stop_listening()
        except Exception:
            logger.exception("stop_listening failed during shutdown")

    def _run_bg(self, name: str, fn) -> None:
        if self._busy_thread is not None and self._busy_thread.is_alive():
            logger.info("Ignoring %s: a power operation is already running", name)
            return
        self._busy_thread = threading.Thread(target=fn, name=f"ALICE-{name}", daemon=True)
        self._busy_thread.start()

    def _wait_for_runtime(self, timeout: float = 40.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self._make_lifecycle() is not None:
                return True
            time.sleep(0.25)
        return False

    # ---- power actions -------------------------------------------------
    def start_alice(self) -> None:
        """Launch: start runtime if needed, then connect + load + verify the model."""
        if self.power in (PowerState.STARTING, PowerState.LOADING_MODEL):
            return
        self.powered_off = False
        if self.worker is not None and not self.worker.isRunning():
            self.worker.start()

        def job():
            if not self._wait_for_runtime():
                self.power_changed.emit(PowerState.ERROR, "ALICE runtime did not start.")
                return
            self.lifecycle.start()   # no-op if already READY/starting: never loads twice
        self._run_bg("start", job)

    def unload_model(self, explicit: bool = True) -> None:
        if self.lifecycle is None:
            return
        self._run_bg("unload", lambda: self.lifecycle.eject(explicit=explicit))

    def power_off(self, explicit_eject: bool = False) -> None:
        if self.lifecycle is None:
            self.powered_off = True
            return
        self.powered_off = True
        self.dashboard.force_stop_voice()          # GUI thread: stop mic + reset buttons
        self._run_bg("poweroff", lambda: self.lifecycle.power_off(explicit_eject=explicit_eject))

    def shutdown_by_voice(self, eject: bool) -> None:
        """Voice command recognised: affects ALICE only, never Windows."""
        self.power_off(explicit_eject=bool(eject))

    def handle_action(self, action: str) -> None:
        d = self.dashboard
        if action in ("start", "load_model"):
            self.start_alice()
        elif action == "start_voice":
            d.toggle_voice()
        elif action == "stop_voice":
            d.stop_voice()
        elif action == "unload_model":
            self.unload_model(explicit=True)
        elif action == "power_off":
            self.power_off(False)
        elif action == "open_settings":
            d.show_dashboard(); d.show_page("settings")
        elif action == "open_dashboard":
            d.show_dashboard()
        elif action == "exit":
            d.exit_application()

    def on_orb_hidden(self) -> None:
        """Orb closed/hidden: unload (only a model ALICE loaded) if the user chose that."""
        if self.lifecycle is not None and getattr(self.dashboard, "unload_on_orb_hide", lambda: False)():
            if self.power == PowerState.READY:
                self.power_off(False)

    # ---- real-event slots (GUI thread) ----------------------------------
    def _on_power(self, state: PowerState, detail: str) -> None:
        self.power, self.power_detail = state, detail
        if self.lifecycle is not None and self.worker is not None:
            rm = getattr(getattr(self.worker, "runtime", None), "runtime", None)
            if rm is not None and state in (PowerState.READY, PowerState.OFF):
                # Keep the existing RuntimeManager's flag truthful (UI-side sync only).
                rm.model_loaded = state == PowerState.READY
                if state == PowerState.OFF:
                    rm.current_model = None
        if state == PowerState.ERROR:
            self._flash(OrbState.ERROR, self.ERROR_MS)
        self._refresh_visuals()

    def _on_runtime_ready(self, connected: bool, detail: str) -> None:
        # One read-only probe (never loads) so the Orb reflects reality at startup.
        if connected and self._make_lifecycle() is not None:
            threading.Thread(target=self.lifecycle.probe, daemon=True, name="ALICE-probe").start()

    def _on_listening(self, active: bool) -> None:
        self.listening = active
        if active:
            self._level_timer.start()
        else:
            self._level_timer.stop()
            if self.orb is not None:
                self.orb.set_audio_level(None)
        self._refresh_visuals()

    def _on_transcribing(self, active: bool) -> None:
        self._set_thinking(active, source="transcribe")

    def _on_speaking(self, active: bool) -> None:
        self.speaking = active
        self._refresh_visuals()

    def _on_worker_state(self, text: str) -> None:
        self._set_thinking(text == "Thinking", source="runtime")

    def _set_thinking(self, active: bool, source: str) -> None:
        flags = self.__dict__.setdefault("_think_sources", set())
        (flags.add if active else flags.discard)(source)
        self.thinking = bool(flags)
        (self._idle.clear if self.thinking else self._idle.set)()
        self._refresh_visuals()

    def _on_response(self, _answer: str) -> None:
        self._flash(OrbState.SUCCESS, self.SUCCESS_MS)
        self._reprobe()

    def _on_error(self, _message: str) -> None:
        self._flash(OrbState.ERROR, self.ERROR_MS)
        self._reprobe()

    def _reprobe(self) -> None:
        if self.lifecycle is not None and not self.lifecycle.is_busy:
            threading.Thread(target=self.lifecycle.probe, daemon=True, name="ALICE-probe").start()

    def _flash(self, state: OrbState, ms: int) -> None:
        self.transient = state
        self._transient_timer.start(ms)
        self._refresh_visuals()

    def _clear_transient(self) -> None:
        self.transient = None
        self._refresh_visuals()

    def _poll_audio_level(self) -> None:
        """Real RMS of the latest captured microphone frame (read-only)."""
        if self.orb is None:
            return
        level = None
        try:
            import numpy as np
            with self.pipeline._audio_lock:
                frame = self.pipeline._frames[-1] if self.pipeline._frames else None
            if frame is not None:
                rms = float(np.sqrt(np.mean(np.square(frame))))
                level = min(1.0, rms * 8.0)
        except Exception:
            level = None
        self.orb.set_audio_level(level)

    def current_state(self) -> OrbState:
        return resolve_state(self.power, listening=self.listening, thinking=self.thinking,
                             speaking=self.speaking, transient=self.transient)

    def _refresh_visuals(self) -> None:
        state = self.current_state()
        if self.orb is not None:
            self.orb.set_state(state)
        self.state_changed.emit(state)
