from __future__ import annotations

from types import SimpleNamespace

import pytest

from alice.dashboard.model_lifecycle import (
    ModelLifecycle, PowerState, match_shutdown_command,
)


class FakeAdapter:
    """Mocked LM Studio adapter: mimics list_models/load_model/unload_model."""

    def __init__(self, loaded=False, server_up=True, load_ok=True, unload_ok=True, unload_effective=True):
        self.loaded = loaded
        self.server_up = server_up
        self.load_ok = load_ok
        self.unload_ok = unload_ok
        self.unload_effective = unload_effective
        self.load_calls = 0
        self.unload_calls = 0
        self.last_error = None

    def start_runtime(self):
        if not self.server_up:
            self.last_error = "LM Studio is not available."
        return self.server_up

    def list_models(self):
        return [{"id": "qwen", "name": "qwen", "loaded": self.loaded,
                 "loaded_instances": [{"id": "qwen"}] if self.loaded else []}]

    def _resolve_model(self, requested):
        return self.list_models()[0]

    def load_model(self, name):
        if self.loaded:
            return True
        self.load_calls += 1
        if not self.load_ok:
            self.last_error = "load failed"
            return False
        self.loaded = True
        return True

    def unload_model(self):
        self.unload_calls += 1
        if not self.unload_ok:
            self.last_error = "unload failed"
            return False
        if self.unload_effective:
            self.loaded = False
        return True


def make(adapter):
    states = []
    cfg = SimpleNamespace(ai=SimpleNamespace(model_name="qwen"))
    lc = ModelLifecycle(adapter, cfg, on_state=lambda s, d: states.append(s))
    return lc, states


def test_launch_loads_model_and_reports_ready_only_after_verify():
    adapter = FakeAdapter()
    lc, states = make(adapter)
    assert lc.start() is True
    assert adapter.load_calls == 1
    assert states == [PowerState.STARTING, PowerState.LOADING_MODEL, PowerState.READY]
    assert states.index(PowerState.READY) > states.index(PowerState.LOADING_MODEL)


def test_not_ready_while_loading():
    seen = []
    adapter = FakeAdapter()
    original = adapter.load_model

    def slow_load(name):
        seen.append(lc.state)
        return original(name)

    adapter.load_model = slow_load
    lc, _ = make(adapter)
    lc.start()
    assert seen == [PowerState.LOADING_MODEL]
    assert lc.state == PowerState.READY


def test_second_start_does_not_load_twice():
    adapter = FakeAdapter()
    lc, _ = make(adapter)
    lc.start()
    lc.start()
    assert adapter.load_calls == 1


def test_already_loaded_model_is_reused_not_loaded():
    adapter = FakeAdapter(loaded=True)
    lc, states = make(adapter)
    assert lc.start() is True
    assert adapter.load_calls == 0
    assert PowerState.LOADING_MODEL not in states
    assert lc.loaded_by_alice is False


def test_load_failure_goes_to_error_never_ready():
    lc, states = make(FakeAdapter(load_ok=False))
    assert lc.start() is False
    assert lc.state == PowerState.ERROR
    assert PowerState.READY not in states


def test_server_unavailable_goes_to_error():
    lc, _ = make(FakeAdapter(server_up=False))
    assert lc.start() is False
    assert lc.state == PowerState.ERROR


def test_eject_requests_and_verifies_unload():
    adapter = FakeAdapter()
    lc, _ = make(adapter)
    lc.start()
    assert lc.eject() is True
    assert adapter.unload_calls == 1
    assert adapter.loaded is False
    assert lc.state == PowerState.OFF


def test_failed_unload_produces_error():
    adapter = FakeAdapter(unload_ok=False)
    lc, _ = make(adapter)
    lc.start()
    assert lc.eject() is False
    assert lc.state == PowerState.ERROR


def test_unload_that_does_not_take_effect_produces_error():
    adapter = FakeAdapter(unload_effective=False)
    lc, _ = make(adapter)
    lc.start()
    assert lc.eject() is False
    assert lc.state == PowerState.ERROR


def test_external_model_not_unloaded_unless_explicit():
    adapter = FakeAdapter(loaded=True)
    lc, _ = make(adapter)
    lc.start()
    assert lc.power_off() is True
    assert adapter.unload_calls == 0
    assert adapter.loaded is True
    lc.start()
    assert lc.power_off(explicit_eject=True) is True
    assert adapter.unload_calls == 1
    assert adapter.loaded is False


def test_restart_after_shutdown_loads_again():
    adapter = FakeAdapter()
    lc, _ = make(adapter)
    lc.start()
    lc.power_off()
    assert lc.state == PowerState.OFF
    lc.start()
    assert adapter.load_calls == 2
    assert lc.state == PowerState.READY


def test_power_off_runs_stop_hooks_and_nothing_else():
    calls = []
    adapter = FakeAdapter()
    lc, states = make(adapter)
    lc.stop_listening = lambda: calls.append("listen")
    lc.stop_speaking = lambda: calls.append("speak")
    lc.cancel_active_request = lambda: calls.append("cancel")
    lc.start()
    lc.power_off()
    assert calls == ["listen", "speak", "cancel"]
    assert PowerState.STOPPING in states and PowerState.EJECTING in states
    assert states[-1] == PowerState.OFF


def test_dashboard_startup_alone_does_not_load_model():
    # Constructing the controller (what the dashboard does) must not touch LM Studio.
    adapter = FakeAdapter()
    lc, states = make(adapter)
    assert lc.state == PowerState.OFF
    assert adapter.load_calls == 0 and states == []


def test_power_off_never_touches_windows(monkeypatch):
    import os
    import subprocess
    forbidden = []
    monkeypatch.setattr(os, "system", lambda *a, **k: forbidden.append("os.system"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: forbidden.append("run"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: forbidden.append("Popen"))
    adapter = FakeAdapter()
    lc, _ = make(adapter)
    lc.start()
    lc.power_off()
    assert forbidden == []
    import alice.dashboard.model_lifecycle as module
    source = open(module.__file__, encoding="utf-8").read()
    for word in ("shutdown /", "ExitWindows", "rundll32", "SetSuspendState", "os.system"):
        assert word not in source


@pytest.mark.parametrize("phrase", [
    "Turn off ALICE.", "Shut down.", "Cut it.", "Stop ALICE", "Power off",
    "hey alice, please shut down", "Turn off.", "power off alice",
])
def test_shutdown_phrases_power_off(phrase):
    match = match_shutdown_command(phrase)
    assert match is not None and match["eject"] is False


@pytest.mark.parametrize("phrase", ["Unload the model.", "Eject the model", "eject model"])
def test_eject_phrases_are_explicit(phrase):
    match = match_shutdown_command(phrase)
    assert match is not None and match["eject"] is True


@pytest.mark.parametrize("phrase", [
    "how do I shut down windows", "please cut it into pieces", "stop the music",
    "restart the computer", "what is the weather", "", "log me out",
])
def test_normal_sentences_do_not_match(phrase):
    assert match_shutdown_command(phrase) is None
