#!/usr/bin/env python3
"""
Main dashboard window for ALICE using PySide6.
Provides the primary user interface with multiple sections.
"""

import sys
import logging
from typing import Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QSplitter,
    QListWidget, QListWidgetItem, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)


class Dashboard(QMainWindow):
    """Main ALICE dashboard window."""

    def __init__(self, config: Any, orb: Any):
        super().__init__()
        self.config = config
        self.orb = orb
        self.setWindowTitle("ALICE - Autonomous Local Intelligence & Computer Engine")
        self.resize(1000, 700)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dashboard UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Header
        header = QLabel("ALICE")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Status bar
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.status_label)

        # Tab widget
        self.tabs = QTabWidget()

        # Home tab
        home_tab = QWidget()
        home_layout = QVBoxLayout(home_tab)
        home_layout.addWidget(QLabel("Welcome to ALICE"))
        self.tabs.addTab(home_tab, "Home")

        # Chat tab
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Type a message or speak...")
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send_message)
        chat_layout.addWidget(self.chat_area)
        chat_layout.addWidget(self.chat_input)
        chat_layout.addWidget(self.send_button)
        self.tabs.addTab(chat_tab, "Chat")

        # Computer Control tab
        computer_tab = QWidget()
        computer_layout = QVBoxLayout(computer_tab)
        computer_layout.addWidget(QLabel("Computer Control"))
        self.app_list = QListWidget()
        self.app_list.addItem("No running applications")
        computer_layout.addWidget(self.app_list)
        self.tabs.addTab(computer_tab, "Computer Control")

        # System Monitor tab
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.addWidget(QLabel("System Monitor"))
        self.cpu_label = QLabel("CPU: 0%")
        self.ram_label = QLabel("RAM: 0%")
        self.vram_label = QLabel("VRAM: 0 MB")
        system_layout.addWidget(self.cpu_label)
        system_layout.addWidget(self.ram_label)
        system_layout.addWidget(self.vram_label)
        self.tabs.addTab(system_tab, "System Monitor")

        # Settings tab
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.addWidget(QLabel("Settings"))
        self.tabs.addTab(settings_tab, "Settings")

        layout.addWidget(self.tabs)

        # Timer for status updates
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status)
        self.timer.start(2000)

    def _send_message(self):
        """Send a chat message."""
        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        self.chat_area.append(f"\nYou: {text}")
        self.chat_input.clear()
        # In production, this would send to AI runtime

    def _update_status(self):
        """Update dashboard status."""
        if self.orb:
            status = self.orb.get_status()
            self.status_label.setText(f"Status: {status['state']}")


def run_dashboard(config: Any, orb: Any):
    """Run the dashboard application."""
    app = QApplication(sys.argv)
    dashboard = Dashboard(config, orb)
    dashboard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    from alice.core.config import Config
    from alice.orb.orb import Orb
    app = QApplication(sys.argv)
    config = Config.load()
    orb = Orb(config)
    dashboard = Dashboard(config, orb)
    dashboard.show()
    sys.exit(app.exec())
