from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from alice.dashboard.model_lifecycle import PowerState
from alice.dashboard.orb_state import OrbState, menu_actions_for, resolve_state
from alice.dashboard.widgets.orb_overlay import OrbOverlay, OrbPreferences, PROFILES


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def orb(app, tmp_path):
    prefs = OrbPreferences(QSettings(str(tmp_path / "orb.ini"), QSettings.IniFormat))
    w = OrbOverlay(prefs)
    yield w
    w.close()


# ---- pure state resolution ------------------------------------------------
def test_ready_only_when_power_ready():
    for p in (PowerState.OFF, PowerState.STARTING, PowerState.LOADING_MODEL):
        assert resolve_state(p) != OrbState.READY
    assert resolve_state(PowerState.READY) == OrbState.READY


def test_power_states_override_activity_flags():
    assert resolve_state(PowerState.LOADING_MODEL, listening=True) == OrbState.LOADING_MODEL
    assert resolve_state(PowerState.EJECTING, speaking=True) == OrbState.EJECTING
    assert resolve_state(PowerState.ERROR, thinking=True) == OrbState.ERROR


def test_activity_priority_when_ready():
    r = PowerState.READY
    assert resolve_state(r, listening=True) == OrbState.LISTENING
    assert resolve_state(r, speaking=True) == OrbState.SPEAKING
    assert resolve_state(r, thinking=True) == OrbState.THINKING
    assert resolve_state(r, thinking=True, transient=OrbState.SUCCESS) == OrbState.SUCCESS
    assert resolve_state(r) == OrbState.READY


def test_every_state_has_a_profile_and_label():
    for s in OrbState:
        assert s in PROFILES


def test_menu_only_lists_valid_actions():
    off = [a for a, _ in menu_actions_for(OrbState.OFF)]
    assert "start" in off and "power_off" not in off and "unload_model" not in off
    ready = [a for a, _ in menu_actions_for(OrbState.READY)]
    assert "start_voice" in ready and "power_off" in ready and "stop_voice" not in ready
    listening = [a for a, _ in menu_actions_for(OrbState.LISTENING)]
    assert "stop_voice" in listening and "start_voice" not in listening
    for state in OrbState:
        ids = [a for a, _ in menu_actions_for(state)]
        assert {"open_dashboard", "open_settings", "hide_orb", "exit"} <= set(ids)


# ---- widget ---------------------------------------------------------------
def test_window_flags_and_transparency(orb):
    assert orb.windowFlags() & Qt.WindowStaysOnTopHint
    assert orb.windowFlags() & Qt.FramelessWindowHint
    assert orb.testAttribute(Qt.WA_TranslucentBackground)


def test_state_transition_is_smooth_not_instant(orb):
    orb.set_state(OrbState.LISTENING)
    orb.tick(0.016)
    assert PROFILES[OrbState.OFF]["core"] < orb._cur["core"] < PROFILES[OrbState.LISTENING]["core"]
    for _ in range(200):
        orb.tick(0.05)
    assert orb._cur["core"] == pytest.approx(PROFILES[OrbState.LISTENING]["core"], abs=0.02)


def test_no_fake_audio_level(orb):
    orb.set_state(OrbState.LISTENING)
    assert orb.audio_level is None
    orb.set_audio_level(0.4)
    assert orb.audio_level == 0.4
    orb.set_audio_level(None)
    assert orb.audio_level is None


def test_animation_timer_stops_when_hidden_and_when_off(orb):
    orb.show(); orb.set_state(OrbState.READY)
    assert orb._timer.isActive()
    orb.hide()
    assert not orb._timer.isActive()
    orb.show(); orb.set_state(OrbState.OFF)
    for _ in range(100):
        orb.tick(0.1)
    orb._on_tick()
    assert not orb._timer.isActive()


def test_renders_all_states_without_error(orb):
    orb.show()
    for s in OrbState:
        orb.set_state(s)
        orb.set_audio_level(0.5 if s == OrbState.LISTENING else None)
        for _ in range(5):
            orb.tick(0.03)
        assert not orb.grab().isNull()


def test_single_click_ready_toggles_voice(orb, qtbot_free=None):
    got = []
    orb.toggle_voice.connect(lambda: got.append("voice"))
    orb.start_requested.connect(lambda: got.append("start"))
    orb.set_state(OrbState.READY)
    QTest.mouseClick(orb, Qt.LeftButton, pos=orb.rect().center())
    QTest.qWait(QApplication.doubleClickInterval() + 80)
    assert got == ["voice"]


def test_single_click_off_requests_start_and_busy_ignored(orb):
    got = []
    orb.start_requested.connect(lambda: got.append("start"))
    orb.toggle_voice.connect(lambda: got.append("voice"))
    orb.set_state(OrbState.OFF)
    QTest.mouseClick(orb, Qt.LeftButton, pos=orb.rect().center())
    QTest.qWait(QApplication.doubleClickInterval() + 80)
    orb.set_state(OrbState.LOADING_MODEL)
    QTest.mouseClick(orb, Qt.LeftButton, pos=orb.rect().center())
    QTest.qWait(QApplication.doubleClickInterval() + 80)
    assert got == ["start"]


def test_double_click_opens_dashboard_without_single_click(orb):
    got = []
    orb.open_dashboard.connect(lambda: got.append("open"))
    orb.toggle_voice.connect(lambda: got.append("voice"))
    orb.set_state(OrbState.READY)
    QTest.mouseDClick(orb, Qt.LeftButton, pos=orb.rect().center())
    QTest.qWait(QApplication.doubleClickInterval() + 80)
    assert "open" in got and "voice" not in got


def test_drag_moves_orb_and_does_not_click(orb):
    got = []
    orb.toggle_voice.connect(lambda: got.append("voice"))
    orb.set_state(OrbState.READY)
    orb.show(); orb.move(200, 200)
    start = orb.frameGeometry().topLeft()
    c = orb.rect().center()
    QTest.mousePress(orb, Qt.LeftButton, pos=c)
    QTest.mouseMove(orb, c + QPoint(60, 40))
    QTest.mouseRelease(orb, Qt.LeftButton, pos=c + QPoint(60, 40))
    QTest.qWait(QApplication.doubleClickInterval() + 80)
    assert orb.frameGeometry().topLeft() != start
    assert got == []
    assert orb.prefs.position is not None


def test_clamp_keeps_orb_on_screen(orb, app):
    area = app.primaryScreen().availableGeometry()
    p = orb.clamp_to_screen(QPoint(area.right() + 5000, area.bottom() + 5000))
    assert p.x() + orb.width() <= area.right() + 1
    assert p.y() + orb.height() <= area.bottom() + 1
    p = orb.clamp_to_screen(QPoint(-9000, -9000))
    assert p.x() >= area.left() and p.y() >= area.top()


def test_preferences_persist_and_clamp(tmp_path):
    path = str(tmp_path / "p.ini")
    a = OrbPreferences(QSettings(path, QSettings.IniFormat))
    a.size = 120; a.opacity = 0.7; a.intensity = 0.4; a.enabled = False
    a.save_position(QPoint(33, 44)); a.s.sync()
    b = OrbPreferences(QSettings(path, QSettings.IniFormat))
    assert (b.size, round(b.opacity, 2), round(b.intensity, 2), b.enabled) == (120, 0.7, 0.4, False)
    assert b.position == QPoint(33, 44)
    b.size = 5000
    assert b.size == 240


def test_hide_orb_does_not_quit_app(orb, app):
    orb.show(); orb.hide_orb()
    assert not orb.isVisible()
    assert QApplication.instance() is app
    assert orb.prefs.enabled is False
