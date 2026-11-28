"""Orb-controlled model power and ejection.

A small, isolated controller that sits *on top of* the existing LM Studio
adapter (``alice.ai.lmstudio_adapter.LMStudioAdapter``).  It adds no new
endpoints: loading and unloading go through the adapter's existing
``/api/v1/models``, ``/api/v1/models/load`` and ``/api/v1/models/unload``
calls.  It is pure Python (no Qt) so it can be tested with a mocked adapter
and driven from any worker thread.

Rules enforced here:
  * READY is only reported after the API confirms the model has a loaded
    instance.
  * A model that was already loaded is reused, never loaded twice, and is not
    unloaded on power-off unless the user explicitly asked to eject it.
  * Unload is verified by re-listing models; failure produces ERROR.
  * Shutdown voice phrases only ever affect ALICE.  Nothing in this module can
    shut down, restart, sleep or log out Windows.
"""
from __future__ import annotations

import logging
import re
import threading
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class PowerState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    LOADING_MODEL = "loading_model"
    READY = "ready"
    STOPPING = "stopping"
    EJECTING = "ejecting"
    ERROR = "error"


StateCallback = Callable[[PowerState, str], None]


# --------------------------------------------------------------------------
# Voice shutdown phrases
# --------------------------------------------------------------------------
_FILLER = {"alice", "hey", "ok", "okay", "please", "now", "the", "a", "just", "can", "you", "could"}

# (normalized phrase, explicit_eject)
_SHUTDOWN_PHRASES: dict[str, bool] = {
    "turn off": False,
    "turn off alice": False,
    "turn alice off": False,
    "shut down": False,
    "shut down alice": False,
    "shutdown": False,
    "shut alice down": False,
    "cut it": False,
    "stop alice": False,
    "power off": False,
    "power off alice": False,
    "power down": False,
    "unload the model": True,
    "unload model": True,
    "unload": True,
    "eject the model": True,
    "eject model": True,
    "eject": True,
}


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    return " ".join(cleaned.split())


def match_shutdown_command(text: str) -> Optional[dict]:
    """Return ``{"eject": bool}`` if *text* is a shutdown command, else None.

    The whole utterance must be the command (optionally wrapped in filler such
    as "hey alice, please ...").  Sentences that merely contain these words
    ("how do I shut down Windows") do not match.  Matching is deliberately
    conservative, and a match only ever means "power off ALICE".
    """
    normalized = _normalize(text)
    if not normalized:
        return None
    words = normalized.split()
    # Strip leading / trailing filler words only.
    while words and words[0] in _FILLER:
        words.pop(0)
    while words and words[-1] in _FILLER:
        words.pop()
    candidate = " ".join(words)
    if candidate in _SHUTDOWN_PHRASES:
        return {"eject": _SHUTDOWN_PHRASES[candidate]}
    # Re-try with "alice" kept (e.g. "turn off alice").
    words = normalized.split()
    keep = {w for w in _FILLER if w != "alice"}
    while words and words[0] in keep:
        words.pop(0)
    while words and words[-1] in keep:
        words.pop()
    candidate = " ".join(words)
    if candidate in _SHUTDOWN_PHRASES:
        return {"eject": _SHUTDOWN_PHRASES[candidate]}
    return None


# --------------------------------------------------------------------------
# Lifecycle controller
# --------------------------------------------------------------------------
class ModelLifecycle:
    """Load / verify / unload the configured LM Studio model."""

    def __init__(self, adapter: Any, config: Any, on_state: Optional[StateCallback] = None):
        self.adapter = adapter
        self.config = config
        self._on_state = on_state
        self._lock = threading.RLock()
        self.state: PowerState = PowerState.OFF
        self.detail: str = ""
        self.loaded_by_alice: bool = False
        self.model_id: Optional[str] = None
        self._known_unloaded = False
        # Voice pipeline hooks supplied by the UI controller (existing instance).
        self.stop_listening: Optional[Callable[[], None]] = None
        self.stop_speaking: Optional[Callable[[], None]] = None
        self.cancel_active_request: Optional[Callable[[], None]] = None

    # -- helpers ----------------------------------------------------------
    def _set(self, state: PowerState, detail: str = "") -> None:
        self.state = state
        self.detail = detail
        logger.info("Model power state: %s %s", state.value, detail)
        if self._on_state:
            try:
                self._on_state(state, detail)
            except Exception:
                logger.exception("Power state callback failed")

    def _requested_name(self) -> str:
        return str(getattr(getattr(self.config, "ai", None), "model_name", "") or "")

    def _find_loaded(self) -> Optional[dict]:
        """Ask LM Studio which instance of the configured model is loaded."""
        model = self.adapter._resolve_model(self._requested_name())
        # _resolve_model refreshes the list; fetch fresh state for certainty.
        for item in self.adapter.list_models():
            if item.get("id") == model.get("id") and item.get("loaded_instances"):
                return item
        return None

    # -- public API -------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return self.state == PowerState.READY

    @property
    def is_busy(self) -> bool:
        return self.state in (
            PowerState.STARTING, PowerState.LOADING_MODEL,
            PowerState.STOPPING, PowerState.EJECTING,
        )

    def start(self) -> bool:
        """Connect to LM Studio, reuse or load the model, verify, then READY."""
        with self._lock:
            if self.state in (PowerState.READY, PowerState.STARTING, PowerState.LOADING_MODEL):
                return self.state == PowerState.READY
            try:
                self._set(PowerState.STARTING, "Connecting to LM Studio")
                if not self.adapter.start_runtime():
                    raise RuntimeError(
                        getattr(self.adapter, "last_error", None) or "LM Studio is not available."
                    )
                already = self._find_loaded()
                if already is not None:
                    # Reuse: tell the adapter which instance to talk to.
                    self.loaded_by_alice = False
                    if not self.adapter.load_model(self._requested_name()):
                        raise RuntimeError(getattr(self.adapter, "last_error", None) or "Could not attach to loaded model.")
                else:
                    self._set(PowerState.LOADING_MODEL, "Loading model")
                    if not self.adapter.load_model(self._requested_name()):
                        raise RuntimeError(
                            getattr(self.adapter, "last_error", None) or "LM Studio could not load the model."
                        )
                    self.loaded_by_alice = True
                verified = self._find_loaded()
                if verified is None:
                    self.loaded_by_alice = False
                    raise RuntimeError("LM Studio did not report the model as loaded.")
                self.model_id = verified.get("id")
                self._set(PowerState.READY, str(self.model_id or ""))
                return True
            except Exception as exc:
                logger.exception("Model start failed")
                self._set(PowerState.ERROR, str(exc))
                return False

    def probe(self) -> PowerState:
        """One read-only check (no loading): reflect what LM Studio reports.

        Used once at dashboard start and once after each request, so the Orb
        never claims READY for a model that is not loaded (e.g. idle-unloaded).
        """
        with self._lock:
            if self.is_busy:
                return self.state
            try:
                loaded = self._find_loaded()
            except Exception as exc:  # server down / model not installed
                logger.info("Model probe: %s", exc)
                if self.state == PowerState.READY:
                    self._set(PowerState.OFF, "Model not available")
                return self.state
            if loaded is not None:
                if self._known_unloaded:
                    self.loaded_by_alice = True  # ALICE's own chat path loaded it
                self._known_unloaded = False
                self.model_id = loaded.get("id")
                if self.state != PowerState.READY:
                    self._set(PowerState.READY, str(self.model_id or ""))
            else:
                self._known_unloaded = True
                self.loaded_by_alice = False
                self.model_id = None
                if self.state != PowerState.OFF:
                    self._set(PowerState.OFF, "Model not loaded")
            return self.state

    def eject(self, *, explicit: bool = False) -> bool:
        """Unload the model and verify.

        ``explicit`` means the user directly asked to unload/eject; only then is
        a model that ALICE did not load itself unloaded.
        """
        with self._lock:
            try:
                self._set(PowerState.EJECTING, "Unloading model")
                if not self.loaded_by_alice and not explicit:
                    logger.info("Model was not loaded by ALICE; leaving it loaded")
                    self.model_id = None
                    self._set(PowerState.OFF, "Model left loaded (not loaded by ALICE)")
                    return True
                ok = bool(self.adapter.unload_model())
                if not ok:
                    raise RuntimeError(
                        getattr(self.adapter, "last_error", None) or "LM Studio refused to unload the model."
                    )
                if self._find_loaded() is not None:
                    raise RuntimeError("Model is still loaded after the unload request.")
                self.loaded_by_alice = False
                self._known_unloaded = True
                self.model_id = None
                self._set(PowerState.OFF, "Model unloaded")
                return True
            except Exception as exc:
                logger.exception("Model eject failed")
                self._set(PowerState.ERROR, str(exc))
                return False

    def power_off(self, *, explicit_eject: bool = False) -> bool:
        """Stop listening/speaking, finish the request safely, unload, go OFF."""
        with self._lock:
            self._set(PowerState.STOPPING, "Shutting down session")
            for hook in (self.stop_listening, self.stop_speaking, self.cancel_active_request):
                if hook:
                    try:
                        hook()
                    except Exception:
                        logger.exception("Shutdown hook failed")
            return self.eject(explicit=explicit_eject)
