"""Floating, always-on-top animated ALICE Orb (pure QPainter, no extra deps)."""
from __future__ import annotations

import math
import random
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer, Signal, QPoint
from PySide6.QtGui import (
    QAction, QColor, QConicalGradient, QGuiApplication, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient, QBrush,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from alice.dashboard import theme
from alice.dashboard.orb_state import LABELS, OrbState, menu_actions_for

# Per-state visual targets. Every value is smoothly interpolated toward these.
#   core: core brightness 0-1, ring: ring speed (rad/s), breath: scale amplitude,
#   rate: particles/sec, wave: wave amplitude 0-1, dim: overall dimming (OFF)
PROFILES = {
    OrbState.OFF:           dict(core=0.08, ring=0.0, breath=0.0,  rate=0.0, wave=0.0, dim=0.55, color=theme.TEXT_MUTED),
    OrbState.STARTING:      dict(core=0.45, ring=1.2, breath=0.02, rate=2.0, wave=0.0, dim=0.2,  color=theme.BLUE),
    OrbState.LOADING_MODEL: dict(core=0.55, ring=1.8, breath=0.03, rate=4.0, wave=0.0, dim=0.1,  color=theme.VIOLET),
    OrbState.READY:         dict(core=0.50, ring=0.25, breath=0.035, rate=0.6, wave=0.0, dim=0.0, color=theme.BLUE),
    OrbState.LISTENING:     dict(core=0.90, ring=0.9, breath=0.02, rate=1.5, wave=1.0, dim=0.0, color=theme.CYAN),
    OrbState.THINKING:      dict(core=0.75, ring=2.6, breath=0.03, rate=7.0, wave=0.0, dim=0.0, color=theme.VIOLET),
    OrbState.SPEAKING:      dict(core=0.85, ring=1.1, breath=0.05, rate=2.5, wave=0.7, dim=0.0, color=theme.CYAN),
    OrbState.SUCCESS:       dict(core=0.85, ring=0.6, breath=0.06, rate=3.0, wave=0.0, dim=0.0, color=theme.SUCCESS),
    OrbState.ERROR:         dict(core=0.55, ring=0.3, breath=0.02, rate=0.5, wave=0.0, dim=0.0, color=theme.ERROR),
    OrbState.STOPPING:      dict(core=0.30, ring=0.8, breath=0.02, rate=0.0, wave=0.0, dim=0.3,  color=theme.BLUE),
    OrbState.EJECTING:      dict(core=0.30, ring=1.4, breath=0.02, rate=1.0, wave=0.0, dim=0.3,  color=theme.VIOLET),
}


class OrbPreferences:
    """UI-only persistence (QSettings); the core ALICE config format is untouched."""

    def __init__(self, settings: Optional[QSettings] = None, defaults=None):
        self.s = settings or QSettings("ALICE", "Orb")
        d = defaults
        self.default_size = int(getattr(d, "size", 96) or 96)
        self.default_opacity = float(getattr(d, "opacity", 0.95) or 0.95)

    def _get(self, key, default, typ):
        try:
            return self.s.value(key, default, type=typ)
        except Exception:
            return default

    @property
    def enabled(self) -> bool: return bool(self._get("enabled", True, bool))
    @enabled.setter
    def enabled(self, v: bool): self.s.setValue("enabled", bool(v))
    @property
    def start_with_alice(self) -> bool: return bool(self._get("start_with_alice", True, bool))
    @start_with_alice.setter
    def start_with_alice(self, v: bool): self.s.setValue("start_with_alice", bool(v))
    @property
    def size(self) -> int: return max(64, min(240, int(self._get("size", self.default_size, int))))
    @size.setter
    def size(self, v: int): self.s.setValue("size", int(v))
    @property
    def opacity(self) -> float: return max(0.3, min(1.0, float(self._get("opacity", self.default_opacity, float))))
    @opacity.setter
    def opacity(self, v: float): self.s.setValue("opacity", float(v))
    @property
    def intensity(self) -> float: return max(0.0, min(1.0, float(self._get("intensity", 0.8, float))))
    @intensity.setter
    def intensity(self, v: float): self.s.setValue("intensity", float(v))
    @property
    def position(self) -> Optional[QPoint]:
        x, y = self._get("pos_x", None, int), self._get("pos_y", None, int)
        return QPoint(x, y) if x is not None and y is not None else None
    def save_position(self, p: QPoint): self.s.setValue("pos_x", p.x()); self.s.setValue("pos_y", p.y())


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(_lerp(a.red(), b.red(), t)), int(_lerp(a.green(), b.green(), t)),
                  int(_lerp(a.blue(), b.blue(), t)))


class OrbOverlay(QWidget):
    """Transparent frameless orb. Emits intent signals only; it owns no pipeline."""

    toggle_voice = Signal()       # single click while READY/LISTENING
    start_requested = Signal()    # click while OFF/ERROR, or menu
    action_requested = Signal(str)  # menu action id (start_voice, stop_voice, power_off, ...)
    open_dashboard = Signal()
    moved = Signal(QPoint)

    DRAG_THRESHOLD = 5

    def __init__(self, prefs: Optional[OrbPreferences] = None):
        super().__init__(None)
        self.prefs = prefs or OrbPreferences()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)

        self.state = OrbState.OFF
        self.audio_level: Optional[float] = None   # real mic level only; None = unknown
        self._cur = dict(PROFILES[OrbState.OFF], color=QColor(PROFILES[OrbState.OFF]["color"]))
        self._phase = 0.0
        self._ring_angle = 0.0
        self._particles: list[dict] = []
        self._spawn_acc = 0.0
        self._last = time.monotonic()
        self._press: Optional[QPoint] = None
        self._press_offset = QPoint()
        self._dragging = False
        self._click_timer = QTimer(self, singleShot=True)
        self._click_timer.timeout.connect(self._emit_single_click)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._success_timer = QTimer(self, singleShot=True)

        self.apply_preferences()
        self.setToolTip("ALICE — Off")

    # -- preferences ------------------------------------------------------
    def apply_preferences(self) -> None:
        side = int(self.prefs.size * 1.6)
        self.setFixedSize(side, side)
        self.setWindowOpacity(self.prefs.opacity)
        self.update()

    @property
    def orb_diameter(self) -> float:
        return float(self.prefs.size)

    # -- state ------------------------------------------------------------
    def set_state(self, state: OrbState) -> None:
        if state == self.state:
            return
        self.state = state
        self.setToolTip(f"ALICE — {LABELS[state]}")
        self._update_timer()
        self.update()

    def set_audio_level(self, level: Optional[float]) -> None:
        """Feed a REAL microphone level (0-1). Pass None when unavailable."""
        self.audio_level = None if level is None else max(0.0, min(1.0, float(level)))

    def _converged(self) -> bool:
        t = PROFILES[self.state]
        keys = ("core", "ring", "breath", "rate", "wave", "dim")
        return all(abs(self._cur[k] - t[k]) < 0.01 for k in keys) and \
            _lerp_color(self._cur["color"], QColor(t["color"]), 1).rgb() == self._cur["color"].rgb()

    def _needs_animation(self) -> bool:
        if not self.isVisible():
            return False
        if self.state == OrbState.OFF and self._converged() and not self._particles:
            return False
        return True

    def _update_timer(self) -> None:
        if self._needs_animation():
            self._last = time.monotonic()
            if not self._timer.isActive():
                self._timer.start(33)
        else:
            self._timer.stop()

    def showEvent(self, e):  # animate only while visible
        super().showEvent(e)
        self._update_timer()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _on_tick(self) -> None:
        now = time.monotonic()
        self.tick(min(0.1, now - self._last))
        self._last = now
        if not self._needs_animation():
            self._timer.stop()
        self.update()

    def tick(self, dt: float) -> None:
        """Advance animation by dt seconds (public for tests)."""
        inten = self.prefs.intensity
        target = PROFILES[self.state]
        k = 1.0 - math.exp(-dt * 6.0)   # smooth ease toward target
        for key in ("core", "ring", "breath", "rate", "wave", "dim"):
            self._cur[key] = _lerp(self._cur[key], target[key], k)
        self._cur["color"] = _lerp_color(self._cur["color"], QColor(target["color"]), k)
        self._phase += dt
        self._ring_angle = (self._ring_angle + self._cur["ring"] * (0.3 + inten) * dt) % (2 * math.pi)
        self._spawn_acc += self._cur["rate"] * inten * dt
        while self._spawn_acc >= 1.0 and len(self._particles) < 40:
            self._spawn_acc -= 1.0
            self._particles.append(dict(a=random.uniform(0, 2 * math.pi), r=0.45,
                                        v=random.uniform(0.08, 0.22), life=1.0, s=random.uniform(1.2, 2.6)))
        self._spawn_acc = min(self._spawn_acc, 1.0)
        for p in self._particles:
            p["r"] += p["v"] * dt * (1.0 + 0.6 * (self.state == OrbState.THINKING))
            p["a"] += dt * (0.8 if self.state == OrbState.THINKING else 0.2)
            p["life"] -= dt * 0.7
        self._particles = [p for p in self._particles if p["life"] > 0]

    # -- painting ---------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        c = self._cur
        accent: QColor = c["color"]
        dim = 1.0 - c["dim"] * 0.6
        center = QPointF(self.width() / 2, self.height() / 2)
        breathe = 1.0 + c["breath"] * math.sin(self._phase * 1.6)
        if self.state == OrbState.LISTENING and self.audio_level is not None:
            breathe += 0.08 * self.audio_level
        r = self.orb_diameter / 2 * breathe
        p.translate(center)

        # 1. outer glow
        glow = QRadialGradient(QPointF(0, 0), r * 1.55)
        g0 = QColor(accent); g0.setAlphaF(0.34 * dim * (0.5 + c["core"] * 0.5))
        g1 = QColor(accent); g1.setAlphaF(0.0)
        glow.setColorAt(0.55, g0); glow.setColorAt(1.0, g1)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(0, 0), r * 1.55, r * 1.55)

        # 2. glass sphere
        sphere = QRadialGradient(QPointF(-r * 0.25, -r * 0.3), r * 1.25)
        sphere.setColorAt(0.0, QColor(30, 50, 95, int(235 * dim)))
        sphere.setColorAt(0.65, QColor(10, 18, 44, int(235 * dim)))
        edge = QColor(accent); edge.setAlphaF(0.55 * dim)
        sphere.setColorAt(1.0, edge)
        p.setBrush(QBrush(sphere)); p.drawEllipse(QPointF(0, 0), r, r)

        # violet accent crescent
        vio = QColor(theme.VIOLET); vio.setAlphaF(0.22 * dim)
        p.setBrush(vio)
        path = QPainterPath(); path.addEllipse(QPointF(0, 0), r * 0.96, r * 0.96)
        cut = QPainterPath(); cut.addEllipse(QPointF(-r * 0.2, -r * 0.2), r * 0.96, r * 0.96)
        p.drawPath(path.subtracted(cut))

        # 3. rings (three tilted ellipses, rotating at different speeds)
        for i, (scale, tilt, width) in enumerate(((1.12, 0.35, 1.6), (1.0, -0.55, 1.2), (0.82, 0.9, 1.0))):
            p.save()
            p.rotate(math.degrees(self._ring_angle * (1 + i * 0.6) * (-1) ** i) + i * 40)
            cg = QConicalGradient(QPointF(0, 0), 0)
            a0 = QColor(accent); a0.setAlphaF(0.85 * dim)
            a1 = QColor(theme.CYAN if i != 1 else theme.VIOLET); a1.setAlphaF(0.0)
            cg.setColorAt(0.0, a0); cg.setColorAt(0.55, a1); cg.setColorAt(1.0, a0)
            p.setPen(QPen(QBrush(cg), width * max(0.8, self.orb_diameter / 90)))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), r * scale, r * scale * (1 - abs(tilt) * 0.55))
            p.restore()

        # 4. energy core
        pulse = 1.0 + 0.12 * math.sin(self._phase * (5.0 if self.state in (OrbState.THINKING, OrbState.SPEAKING) else 2.0))
        if self.state == OrbState.LISTENING and self.audio_level is not None:
            pulse += 0.5 * self.audio_level
        cr = r * 0.42 * pulse
        core = QRadialGradient(QPointF(0, 0), cr * 1.6)
        w = QColor(255, 255, 255, int(255 * c["core"] * dim))
        m = QColor(accent); m.setAlphaF(0.85 * c["core"] * dim)
        o = QColor(accent); o.setAlphaF(0.0)
        core.setColorAt(0.0, w); core.setColorAt(0.35, m); core.setColorAt(1.0, o)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(core)); p.drawEllipse(QPointF(0, 0), cr * 1.6, cr * 1.6)

        # 5. particles
        for pt in self._particles:
            alpha = max(0.0, min(1.0, pt["life"])) * 0.8 * dim
            pc = QColor(theme.CYAN if int(pt["a"] * 10) % 2 else theme.VIOLET); pc.setAlphaF(alpha)
            p.setBrush(pc)
            x, y = math.cos(pt["a"]) * r * pt["r"] * 1.4, math.sin(pt["a"]) * r * pt["r"] * 1.4
            p.drawEllipse(QPointF(x, y), pt["s"], pt["s"])

        # 6. wave (listening uses real level only; otherwise a flat baseline)
        if c["wave"] > 0.05:
            if self.state == OrbState.LISTENING:
                amp = (self.audio_level or 0.0) * 0.45 * r
            else:  # SPEAKING: decorative state animation
                amp = 0.22 * r * (0.6 + 0.4 * math.sin(self._phase * 3.1))
            wp = QPainterPath(); n = 40
            for i in range(n + 1):
                t = i / n; x = (t - 0.5) * r * 1.3
                env = math.sin(math.pi * t)
                y = math.sin(t * 9 + self._phase * 7) * amp * env
                wp.moveTo(x, y) if i == 0 else wp.lineTo(x, y)
            wc = QColor(255, 255, 255); wc.setAlphaF(0.85 * c["wave"])
            p.setPen(QPen(wc, max(1.5, r / 30), Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
            p.drawPath(wp)

        # 7. glass highlight
        hl = QLinearGradient(QPointF(-r * 0.5, -r * 0.9), QPointF(0, -r * 0.2))
        hl.setColorAt(0.0, QColor(255, 255, 255, int(70 * dim))); hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(hl))
        p.drawEllipse(QRectF(-r * 0.62, -r * 0.92, r * 1.0, r * 0.62))

        # listening indicator dot
        if self.state == OrbState.LISTENING:
            dot = QColor(theme.ERROR); dot.setAlphaF(0.55 + 0.45 * math.sin(self._phase * 6))
            p.setBrush(dot); p.drawEllipse(QPointF(r * 0.78, -r * 0.78), r * 0.09, r * 0.09)
        p.end()

    # -- mouse: click / double-click / drag ------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._press_offset = self._press - self.frameGeometry().topLeft()
            self._dragging = False

    def mouseMoveEvent(self, e) -> None:
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        pos = e.globalPosition().toPoint()
        if not self._dragging and (pos - self._press).manhattanLength() >= self.DRAG_THRESHOLD:
            self._dragging = True
            self._click_timer.stop()
        if self._dragging:
            self.move(self.clamp_to_screen(pos - self._press_offset))

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._press is None:
            return
        was_drag = self._dragging
        self._press = None; self._dragging = False
        if was_drag:
            self.prefs.save_position(self.pos()); self.moved.emit(self.pos())
            return
        # Delay single click so a double click can cancel it.
        self._click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._click_timer.stop()
            self.open_dashboard.emit()

    def _emit_single_click(self) -> None:
        if self.state in (OrbState.OFF, OrbState.ERROR):
            self.start_requested.emit()
        elif self.state in (OrbState.READY, OrbState.LISTENING, OrbState.SUCCESS):
            self.toggle_voice.emit()
        # other states are transient/busy: ignore the click

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        for action_id, label in menu_actions_for(self.state):
            if action_id == "-":
                menu.addSeparator(); continue
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, a=action_id: self._on_menu(a))
            menu.addAction(act)
        menu.exec(e.globalPos())

    def _on_menu(self, action_id: str) -> None:
        if action_id == "hide_orb":
            self.hide_orb()
        elif action_id == "open_dashboard":
            self.open_dashboard.emit()
        else:
            self.action_requested.emit(action_id)

    # -- visibility / position -------------------------------------------
    def hide_orb(self) -> None:
        self.prefs.enabled = False
        self.hide()

    def show_orb(self) -> None:
        self.prefs.enabled = True
        self.restore_position()
        self.show()
        self._update_timer()

    @staticmethod
    def _available_union() -> QRectF:
        rect = QRectF()
        for s in QGuiApplication.screens():
            rect = rect.united(QRectF(s.availableGeometry()))
        return rect

    def clamp_to_screen(self, top_left: QPoint) -> QPoint:
        """Keep the orb fully inside the work area of the nearest monitor."""
        centre = top_left + QPoint(self.width() // 2, self.height() // 2)
        screen = QGuiApplication.screenAt(centre) or QGuiApplication.primaryScreen()
        if screen is None:
            return top_left
        area = screen.availableGeometry()
        x = max(area.left(), min(top_left.x(), area.right() - self.width() + 1))
        y = max(area.top(), min(top_left.y(), area.bottom() - self.height() + 1))
        return QPoint(x, y)

    def restore_position(self) -> None:
        saved = self.prefs.position
        if saved is not None:
            self.move(self.clamp_to_screen(saved))
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                a = screen.availableGeometry()
                self.move(a.right() - self.width() - 24, a.bottom() - self.height() - 24)
