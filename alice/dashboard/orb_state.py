"""Pure-Python Orb state model (no Qt) so state logic is unit-testable."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from alice.dashboard.model_lifecycle import PowerState


class OrbState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    LOADING_MODEL = "loading_model"
    READY = "ready"          # idle: loaded, waiting
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SUCCESS = "success"
    ERROR = "error"
    STOPPING = "stopping"
    EJECTING = "ejecting"


LABELS = {
    OrbState.OFF: "Off", OrbState.STARTING: "Starting", OrbState.LOADING_MODEL: "Loading model",
    OrbState.READY: "Ready", OrbState.LISTENING: "Listening", OrbState.THINKING: "Thinking",
    OrbState.SPEAKING: "Speaking", OrbState.SUCCESS: "Done", OrbState.ERROR: "Error",
    OrbState.STOPPING: "Stopping", OrbState.EJECTING: "Ejecting model",
}

_POWER_TO_ORB = {
    PowerState.OFF: OrbState.OFF,
    PowerState.STARTING: OrbState.STARTING,
    PowerState.LOADING_MODEL: OrbState.LOADING_MODEL,
    PowerState.STOPPING: OrbState.STOPPING,
    PowerState.EJECTING: OrbState.EJECTING,
    PowerState.ERROR: OrbState.ERROR,
}


def resolve_state(power: PowerState, *, listening: bool = False, thinking: bool = False,
                  speaking: bool = False, transient: Optional[OrbState] = None) -> OrbState:
    """Combine real runtime flags into one visual state.

    Power-lifecycle states always win; READY is only shown when the lifecycle
    controller has verified the model is loaded.
    """
    if power in _POWER_TO_ORB:
        return _POWER_TO_ORB[power]
    if transient is not None:
        return transient
    if listening:
        return OrbState.LISTENING
    if speaking:
        return OrbState.SPEAKING
    if thinking:
        return OrbState.THINKING
    return OrbState.READY


def menu_actions_for(state: OrbState) -> list[tuple[str, str]]:
    """Return (action_id, label) pairs valid for *state*; "-" is a separator."""
    items: list[tuple[str, str]] = []
    if state in (OrbState.OFF, OrbState.ERROR):
        items += [("start", "Start ALICE"), ("load_model", "Load Model")]
    elif state == OrbState.LISTENING:
        items += [("stop_voice", "Stop Listening")]
    elif state in (OrbState.READY, OrbState.SUCCESS, OrbState.SPEAKING, OrbState.THINKING):
        if state in (OrbState.READY, OrbState.SUCCESS):
            items += [("start_voice", "Start voice")]
    if state in (OrbState.READY, OrbState.LISTENING, OrbState.SUCCESS, OrbState.SPEAKING, OrbState.THINKING):
        items += [("unload_model", "Unload Model"), ("power_off", "Power Off ALICE")]
    items.append(("-", ""))
    items += [("open_dashboard", "Open Dashboard"), ("open_settings", "Open Settings"),
              ("hide_orb", "Hide Orb"), ("-", ""), ("exit", "Exit Application")]
    return items
