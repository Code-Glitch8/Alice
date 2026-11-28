"""ALICE design system: palette, typography and the global Qt stylesheet.

UI-only module. Every colour and size used by the redesigned dashboard and the
Orb comes from here so the whole app reads as one design system.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# --- Palette ---------------------------------------------------------------
BG_MAIN = "#080B12"
BG_SECONDARY = "#0D1220"
BG_ELEVATED = "#141B2A"
BG_CARD = "#182235"
BLUE = "#438BFF"
CYAN = "#37D9FF"
VIOLET = "#906BFF"
TEXT = "#F4F7FF"
TEXT_MUTED = "#8B9AB4"
SUCCESS = "#42D6A0"
ERROR = "#FF627A"
WARNING = "#FFC857"
BORDER = "rgba(255,255,255,0.07)"
BORDER_STRONG = "rgba(255,255,255,0.14)"

FONT_STACK = ["Segoe UI Variable Display", "Segoe UI", "Inter", "Helvetica Neue", "Arial"]
MONO_STACK = ["Cascadia Code", "Consolas", "Courier New", "monospace"]


def qcolor(hex_or_name: str, alpha: float = 1.0) -> QColor:
    color = QColor(hex_or_name)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def app_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONT_STACK)
    font.setPointSize(size)
    font.setWeight(weight)
    return font


# Type scale (pt). Points scale with Windows DPI, so 100-150%+ stays crisp.
TYPE = {"display": 22, "page": 17, "section": 12, "body": 10, "small": 9, "label": 8}


def stylesheet() -> str:
    f = ", ".join(f'"{n}"' for n in FONT_STACK)
    m = ", ".join(f'"{n}"' for n in MONO_STACK)
    return f"""
* {{ font-family: {f}; outline: none; }}
QMainWindow, QWidget#root {{ background: {BG_MAIN}; }}
QWidget {{ color: {TEXT}; font-size: {TYPE['body']}pt; }}
QToolTip {{ background: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
           padding: 6px 8px; border-radius: 6px; }}

/* Sidebar */
QFrame#sidebar {{ background: {BG_SECONDARY}; border-right: 1px solid {BORDER}; }}
QLabel#brand {{ color: {TEXT}; font-size: {TYPE['display']}pt; font-weight: 800; letter-spacing: 4px; }}
QLabel#brandSmall {{ color: {CYAN}; font-size: {TYPE['section']}pt; font-weight: 800; }}
QLabel#tagline, QLabel#muted {{ color: {TEXT_MUTED}; font-size: {TYPE['label']}pt; letter-spacing: 1px; }}
QPushButton#navButton {{ background: transparent; color: {TEXT_MUTED}; border: none; border-radius: 12px;
    padding: 11px 14px; text-align: left; font-weight: 600; }}
QPushButton#navButton:hover {{ background: rgba(255,255,255,0.05); color: {TEXT}; }}
QPushButton#navButton:checked {{ background: rgba(67,139,255,0.16); color: {TEXT}; }}
QPushButton#navButton:focus {{ border: 1px solid {BLUE}; }}

/* Top bar */
QFrame#topbar {{ background: transparent; border-bottom: 1px solid {BORDER}; }}
QLabel#pageTitle {{ font-size: {TYPE['page']}pt; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: {TYPE['section']}pt; font-weight: 700; }}
QLabel#statusChip {{ background: {BG_ELEVATED}; color: {TEXT_MUTED}; border: 1px solid {BORDER};
    border-radius: 11px; padding: 4px 10px; font-size: {TYPE['small']}pt; }}
QLabel#status {{ color: {TEXT_MUTED}; font-size: {TYPE['small']}pt; }}

/* Cards */
QFrame#card {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#cardElevated {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; border-radius: 16px; }}
QLabel#cardTitle {{ font-size: {TYPE['section']}pt; font-weight: 700; background: transparent; }}
QLabel#cardBody, QLabel#metricValue {{ background: transparent; }}
QLabel#metricValue {{ font-size: {TYPE['page']}pt; font-weight: 700; }}
QLabel#metric {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 12px; }}

/* Inputs */
QTextEdit, QPlainTextEdit, QLineEdit, QListWidget, QComboBox, QSpinBox {{
    background: {BG_ELEVATED}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 10px;
    selection-background-color: {BLUE}; }}
QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {BLUE}; }}
QTextEdit:disabled, QLineEdit:disabled, QComboBox:disabled {{ color: #5B677C; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {BG_ELEVATED}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {BLUE}; padding: 4px; }}
QFrame#composer {{ background: {BG_ELEVATED}; border: 1px solid {BORDER_STRONG}; border-radius: 20px; }}
QFrame#composer[focused="true"] {{ border: 1px solid {BLUE}; }}
QTextEdit#composerInput {{ background: transparent; border: none; padding: 6px; font-size: {TYPE['body'] + 1}pt; }}

/* Buttons */
QPushButton {{ padding: 9px 16px; border-radius: 10px; font-weight: 600; background: {BG_ELEVATED};
    color: {TEXT}; border: 1px solid {BORDER}; min-height: 20px; }}
QPushButton:hover {{ background: #1B2438; border: 1px solid {BORDER_STRONG}; }}
QPushButton:pressed {{ background: #101726; }}
QPushButton:focus {{ border: 1px solid {BLUE}; }}
QPushButton:disabled {{ background: #10151F; color: #566178; border: 1px solid {BORDER}; }}
QPushButton#primaryButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {BLUE},stop:1 {VIOLET});
    color: white; border: none; }}
QPushButton#primaryButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #5B9CFF,stop:1 #A183FF); }}
QPushButton#primaryButton:disabled {{ background: #26314A; color: #7B879C; }}
QPushButton#secondaryButton {{ background: rgba(67,139,255,0.14); color: #BFD8FF; border: 1px solid rgba(67,139,255,0.3); }}
QPushButton#secondaryButton:hover {{ background: rgba(67,139,255,0.24); }}
QPushButton#recordingButton {{ background: rgba(255,98,122,0.18); color: #FFC3CC; border: 1px solid rgba(255,98,122,0.5); }}
QPushButton#dangerButton {{ background: rgba(255,98,122,0.12); color: {ERROR}; border: 1px solid rgba(255,98,122,0.35); }}
QPushButton#dangerButton:hover {{ background: rgba(255,98,122,0.22); }}
QPushButton#iconButton {{ padding: 6px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
    border-radius: 16px; background: transparent; border: none; color: {TEXT_MUTED}; }}
QPushButton#iconButton:hover {{ background: rgba(255,255,255,0.08); color: {TEXT}; }}
QPushButton#closeButton:hover {{ background: rgba(255,98,122,0.85); color: white; }}

QCheckBox {{ spacing: 10px; padding: 4px 0; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {BORDER_STRONG}; background: {BG_ELEVATED}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border: 1px solid {BLUE}; }}
QCheckBox::indicator:focus {{ border: 1px solid {CYAN}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BG_ELEVATED}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {BLUE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QProgressBar {{ background: {BG_ELEVATED}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {BLUE},stop:1 {CYAN}); border-radius: 4px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.14); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.26); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QMenu {{ background: {BG_ELEVATED}; border: 1px solid {BORDER_STRONG}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(67,139,255,0.25); }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QMessageBox {{ background: {BG_SECONDARY}; }}
code, pre {{ font-family: {m}; }}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    app.setFont(app_font(TYPE["body"]))
    app.setStyleSheet(stylesheet())
