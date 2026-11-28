#!/usr/bin/env python3
"""ALICE's functional PySide6 desktop dashboard."""
from __future__ import annotations

import logging
import threading
from typing import Any

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QPushButton, QTextEdit, QListWidget, QCheckBox, QGroupBox,
    QFormLayout, QMessageBox, QLineEdit, QGraphicsOpacityEffect, QProgressBar,
    QSystemTrayIcon, QMenu, QStyle, QComboBox, QSpinBox
)
from PySide6.QtGui import QAction

from alice.dashboard.runtime_worker import RuntimeWorker
from alice.voice.pipeline import VoicePipeline

logger = logging.getLogger(__name__)


class TranscriptionWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, pipeline: VoicePipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline

    def run(self) -> None:
        try:
            self.completed.emit(self.pipeline.recognize())
        except Exception as exc:
            self.failed.emit(str(exc))


class Dashboard(QMainWindow):
    """Main desktop window. All long-running AI/audio work stays off the UI thread."""

    def __init__(self, config: Any, orb: Any = None,
                 runtime_worker: RuntimeWorker | None = None):
        super().__init__()
        self.config = config
        self.orb = orb
        self.runtime_worker = runtime_worker
        self.voice_pipeline = VoicePipeline(config)
        self._transcription_worker: TranscriptionWorker | None = None
        self._voice_recording = False
        self.setWindowTitle("ALICE — Local Windows AI Assistant")
        self.resize(1100, 760)
        self.setMinimumSize(820, 600)
        self._setup_ui()
        self._create_tray()
        self._really_exit = False
        self._connect_runtime()
        self._fade_in()

    def _setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("ALICE")
        brand.setObjectName("brand")
        tagline = QLabel("LOCAL INTELLIGENCE • DESKTOP CONTROL")
        tagline.setObjectName("muted")
        header.addWidget(brand)
        header.addSpacing(14)
        header.addWidget(tagline)
        header.addStretch(1)
        self.status_label = QLabel("Starting local runtime…")
        self.status_label.setObjectName("status")
        header.addWidget(self.status_label)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Chat
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        intro = QLabel("Your local desktop assistant")
        intro.setObjectName("sectionTitle")
        chat_layout.addWidget(intro)
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setPlaceholderText("Your conversation with ALICE will appear here.")
        self.chat_area.append("ALICE: Ready when you are. Connect LM Studio and send a request.")
        chat_layout.addWidget(self.chat_area, 1)

        self.chat_input = QTextEdit()
        self.chat_input.setFixedHeight(88)
        self.chat_input.setPlaceholderText(
            "Ask ALICE a question or request a supported desktop action…  (Ctrl+Enter to send)"
        )
        chat_layout.addWidget(self.chat_input)

        controls = QHBoxLayout()
        self.voice_button = QPushButton("🎙  Start voice")
        self.voice_button.setObjectName("secondaryButton")
        self.voice_button.clicked.connect(self._toggle_voice)
        self.send_button = QPushButton("Send  ➤")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self._send_message)
        self.speak_replies = QCheckBox("Speak replies")
        self.speak_replies.setChecked(False)
        controls.addWidget(self.voice_button)
        controls.addWidget(self.speak_replies)
        controls.addStretch(1)
        controls.addWidget(self.send_button)
        chat_layout.addLayout(controls)
        self.tabs.addTab(chat_tab, "Chat")

        # Computer control information
        computer_tab = QWidget()
        computer_layout = QVBoxLayout(computer_tab)
        computer_layout.addWidget(QLabel("Desktop automation"))
        computer_layout.addWidget(QLabel(
            "Use the Chat tab to ask ALICE to open applications, find and manage files, "
            "control supported windows, use keyboard and mouse actions, or automate browser tasks. "
            "Protected file changes require your approval."
        ))
        self.app_list = QListWidget()
        self.app_list.addItem("Automation tools are available after the local model connects.")
        computer_layout.addWidget(self.app_list, 1)
        self.tabs.addTab(computer_tab, "Computer")

        # System monitor
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.addWidget(QLabel("System monitor"))
        self.cpu_label = QLabel("CPU: —")
        self.ram_label = QLabel("RAM: —")
        self.vram_label = QLabel("GPU memory: not available")
        for item in (self.cpu_label, self.ram_label, self.vram_label):
            item.setObjectName("metric")
            system_layout.addWidget(item)
        self.monitor_bar = QProgressBar()
        self.monitor_bar.setRange(0, 100)
        self.monitor_bar.setFormat("Memory usage %p%")
        system_layout.addWidget(self.monitor_bar)
        system_layout.addStretch(1)
        self.tabs.addTab(system_tab, "System")

        # Settings - preserve Computer Access Manager and add voice/hotkey controls
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.addWidget(QLabel("Settings and permissions"))
        settings_layout.addWidget(QLabel(
            "ALICE operates as your signed-in Windows user. It does not elevate privileges "
            "or bypass Windows security."
        ))

        ai_group = QGroupBox("Local AI Runtime")
        ai_form = QFormLayout(ai_group)
        self.ai_url_edit = QLineEdit(str(self.config.ai.base_url))
        self.model_name_edit = QLineEdit(str(self.config.ai.model_name))
        self.model_name_edit.setPlaceholderText("LM Studio model key or display name")
        ai_form.addRow("LM Studio server URL", self.ai_url_edit)
        ai_form.addRow("Model", self.model_name_edit)
        settings_layout.addWidget(ai_group)

        access_group = QGroupBox("Computer Access Manager")
        access_form = QFormLayout(access_group)
        access_fields = [
            ("search_all_drives", "Search all mounted drives"),
            ("allow_read_files", "Read accessible text files"),
            ("allow_create_files_folders", "Create files and folders"),
            ("allow_edit_files", "Edit existing files"),
            ("allow_move_files", "Move and organize files/folders"),
            ("allow_app_control", "Control applications and windows"),
            ("allow_delete_files", "Delete files and folders"),
        ]
        self.access_checkboxes = {}
        for field, label in access_fields:
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(getattr(self.config.automation, field, True)))
            self.access_checkboxes[field] = checkbox
            access_form.addRow(checkbox)
        settings_layout.addWidget(access_group)

        voice_group = QGroupBox("Voice")
        voice_form = QFormLayout(voice_group)
        self.mute_checkbox = QCheckBox("Microphone muted")
        self.mute_checkbox.setChecked(bool(self.config.voice.mute))
        self.wakeword_checkbox = QCheckBox("Enable wake-word monitoring")
        self.wakeword_checkbox.setChecked(bool(self.config.voice.wake_word_enabled))
        self.wakeword_edit = QLineEdit(str(self.config.voice.wake_word))
        self.mic_device_combo = QComboBox()
        self.mic_device_combo.addItem("System default microphone", None)
        try:
            import sounddevice as sd
            for device_index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels", 0)) > 0:
                    self.mic_device_combo.addItem(str(device.get("name", device_index)), device_index)
        except Exception as exc:
            logger.info("Could not enumerate microphone devices: %s", exc)
        configured_device = self.config.voice.microphone_device
        selected_device = self.mic_device_combo.findData(configured_device)
        self.mic_device_combo.setCurrentIndex(max(0, selected_device))
        self.stt_model_combo = QComboBox()
        self.stt_model_combo.addItems(["tiny", "base", "small", "medium"])
        stt_index = self.stt_model_combo.findText(str(self.config.voice.stt_model))
        self.stt_model_combo.setCurrentIndex(stt_index if stt_index >= 0 else 2)

        self.vad_checkbox = QCheckBox("Use Silero VAD to detect speech and trim silence")
        self.vad_checkbox.setChecked(bool(getattr(self.config.voice, "voice_activity_detection", True)))
        self.vad_checkbox.setToolTip(
            "Silero VAD runs locally and sends speech-only chunks to Faster-Whisper. "
            "If the VAD model cannot load, ALICE falls back to Whisper's built-in VAD."
        )

        self.tts_language_combo = QComboBox()
        self.tts_language_combo.addItem("English (US)", "en-us")
        self.tts_language_combo.addItem("English (UK)", "en-gb")
        self.tts_language_combo.addItem("Hindi", "hi")
        language_index = self.tts_language_combo.findData(
            str(getattr(self.config.voice, "tts_language", "en-us"))
        )
        self.tts_language_combo.setCurrentIndex(language_index if language_index >= 0 else 0)

        self.tts_voice_combo = QComboBox()
        self._refresh_voice_choices()
        self.tts_language_combo.currentIndexChanged.connect(self._refresh_voice_choices)

        self.tts_rate_spin = QSpinBox()
        self.tts_rate_spin.setRange(80, 260)
        self.tts_rate_spin.setValue(int(self.config.voice.tts_rate))
        self.preview_voice_button = QPushButton("Preview selected voice")
        self.preview_voice_button.clicked.connect(self._preview_selected_voice)
        self.voice_model_note = QLabel(
            "Kokoro neural voices are downloaded locally on first use (about 300 MB). "
            "Piper is the fallback when a Piper voice pack is installed; Windows SAPI is the final fallback."
        )
        self.voice_model_note.setWordWrap(True)
        self.voice_model_note.setObjectName("muted")

        self.wakeword_checkbox.setToolTip(
            "Wake-word monitoring requires a compatible local openWakeWord model. "
            "The OMEN / configured keyboard shortcut can activate manual voice capture."
        )
        self.shortcut_edit = QLineEdit(str(self.config.omen.fallback_shortcut))
        voice_form.addRow(self.mute_checkbox)
        voice_form.addRow(self.wakeword_checkbox)
        voice_form.addRow("Wake phrase", self.wakeword_edit)
        voice_form.addRow("Microphone", self.mic_device_combo)
        voice_form.addRow("Speech recognition model", self.stt_model_combo)
        voice_form.addRow(self.vad_checkbox)
        voice_form.addRow("Spoken language", self.tts_language_combo)
        voice_form.addRow("Kokoro voice", self.tts_voice_combo)
        voice_form.addRow(self.preview_voice_button)
        voice_form.addRow(self.voice_model_note)
        voice_form.addRow("Speech rate", self.tts_rate_spin)
        voice_form.addRow("Voice activation shortcut", self.shortcut_edit)
        settings_layout.addWidget(voice_group)

        startup_group = QGroupBox("Windows startup and background")
        startup_form = QFormLayout(startup_group)
        self.startup_checkbox = QCheckBox("Start ALICE when I sign in")
        self.startup_checkbox.setChecked(bool(self.config.startup.start_with_windows))
        self.tray_checkbox = QCheckBox("Keep ALICE running in the system tray when the window is closed")
        self.tray_checkbox.setChecked(bool(self.config.startup.minimize_to_tray))
        startup_form.addRow(self.startup_checkbox)
        startup_form.addRow(self.tray_checkbox)
        settings_layout.addWidget(startup_group)

        self.drive_list_label = QLabel("Drive discovery is available on Windows.")
        self.drive_list_label.setWordWrap(True)
        try:
            from alice.core.access_manager import discover_drive_roots
            self.drive_list_label.setText(
                "Accessible drives: " + (", ".join(str(p) for p in discover_drive_roots()) or "none found")
            )
        except Exception as exc:
            self.drive_list_label.setText(f"Drive discovery unavailable: {exc}")
        settings_layout.addWidget(self.drive_list_label)

        settings_layout.addWidget(QLabel(
            "Safety: overwriting, moving, and deleting files always require explicit confirmation. "
            "Drive roots and critical Windows folders are protected."
        ))
        save_button = QPushButton("Save settings")
        save_button.clicked.connect(self._save_settings)
        settings_layout.addWidget(save_button)
        settings_layout.addStretch(1)
        self.tabs.addTab(settings_tab, "Settings")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_status)
        self.timer.start(2500)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #10141d; color: #e8edf6; font-size: 13px; }
            QLabel#brand { color: #76b8ff; font-size: 26px; font-weight: 800; letter-spacing: 2px; }
            QLabel#muted { color: #8290a6; font-size: 10px; letter-spacing: 1px; }
            QLabel#status { color: #8fd4b1; padding: 7px 12px; border: 1px solid #284d43; border-radius: 12px; }
            QLabel#sectionTitle { font-size: 18px; font-weight: 700; padding: 4px; }
            QLabel#metric { background: #1a2230; border: 1px solid #2b374a; border-radius: 8px; padding: 12px; }
            QTabWidget::pane { border: 1px solid #2b374a; border-radius: 10px; }
            QTabBar::tab { background: #171e2b; padding: 10px 18px; margin-right: 4px; border-radius: 7px; }
            QTabBar::tab:selected { background: #243c5b; color: #9acbff; }
            QTextEdit, QLineEdit, QListWidget { background: #171e2b; border: 1px solid #2b374a; border-radius: 8px; padding: 10px; selection-background-color: #315b85; }
            QGroupBox { border: 1px solid #2b374a; border-radius: 8px; margin-top: 12px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QPushButton { padding: 10px 16px; border-radius: 8px; font-weight: 600; }
            QPushButton#primaryButton { background: #3479c9; color: white; }
            QPushButton#primaryButton:hover { background: #438de0; }
            QPushButton#secondaryButton { background: #26354a; color: #b8d9ff; }
            QPushButton:disabled { background: #303846; color: #8993a3; }
            QCheckBox { spacing: 8px; padding: 4px; }
            QProgressBar { border: 1px solid #2b374a; border-radius: 6px; text-align: center; background: #171e2b; }
            QProgressBar::chunk { background: #3479c9; border-radius: 5px; }
        """)

    def _refresh_voice_choices(self, *_args) -> None:
        """Keep Kokoro voice choices compatible with the selected language."""
        language = str(self.tts_language_combo.currentData() or "en-us")
        voice_options = {
            "en-us": [
                ("Heart — Female", "af_heart"),
                ("Bella — Female", "af_bella"),
                ("Nicole — Female", "af_nicole"),
                ("Sarah — Female", "af_sarah"),
                ("Michael — Male", "am_michael"),
                ("Fenrir — Male", "am_fenrir"),
            ],
            "en-gb": [
                ("Emma — Female", "bf_emma"),
                ("Fable — Male", "bm_fable"),
            ],
            "hi": [
                ("Alpha — Female", "hf_alpha"),
                ("Beta — Female", "hf_beta"),
            ],
        }
        configured = str(getattr(self.config.voice, "tts_voice", "af_heart") or "af_heart")
        options = voice_options.get(language, voice_options["en-us"])
        self.tts_voice_combo.blockSignals(True)
        self.tts_voice_combo.clear()
        selected_index = 0
        for index, (label, voice_id) in enumerate(options):
            self.tts_voice_combo.addItem(label, voice_id)
            if voice_id == configured:
                selected_index = index
        self.tts_voice_combo.setCurrentIndex(selected_index)
        self.tts_voice_combo.blockSignals(False)

    def _preview_selected_voice(self) -> None:
        """Preview the currently selected local Kokoro voice without blocking the UI."""
        self.config.voice.tts_engine = "kokoro"
        self.config.voice.tts_language = str(self.tts_language_combo.currentData() or "en-us")
        self.config.voice.tts_voice = str(self.tts_voice_combo.currentData() or "af_heart")
        self.config.voice.tts_rate = self.tts_rate_spin.value()
        preview_text = (
            "नमस्ते। मैं ALICE हूँ। यह चुनी हुई आवाज़ का परीक्षण है।"
            if self.config.voice.tts_language == "hi"
            else "Hello. I am ALICE. This is a preview of the selected neural voice."
        )
        threading.Thread(
            target=self.voice_pipeline.speak,
            args=(preview_text,),
            name="ALICE-VoicePreview",
            daemon=True,
        ).start()

    def _fade_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade_animation = QPropertyAnimation(effect, b"opacity", self)
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(0.65)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()

    def _connect_runtime(self) -> None:
        if not self.runtime_worker:
            self.status_label.setText("Runtime not attached")
            return
        self.runtime_worker.ready.connect(self._on_runtime_ready)
        self.runtime_worker.response.connect(self._on_response)
        self.runtime_worker.error.connect(self._on_runtime_error)
        self.runtime_worker.state_changed.connect(self.status_label.setText)
        self.runtime_worker.confirmation_requested.connect(self._show_confirmation)
        self.runtime_worker.hotkey_activated.connect(self._activate_voice)
        self.runtime_worker.wake_word_paused.connect(self._begin_voice_recording)

    def _on_runtime_ready(self, connected: bool, detail: str) -> None:
        self.status_label.setText("Connected" if connected else "Offline — LM Studio")
        self.chat_area.append(f"ALICE: {detail}")

    def _send_message(self) -> None:
        message = self.chat_input.toPlainText().strip()
        if not message:
            return
        if not self.runtime_worker:
            self._on_runtime_error("AI runtime is not available.")
            return
        self.chat_area.append(f"\nYou: {message}")
        self.chat_input.clear()
        self.send_button.setEnabled(False)
        self.runtime_worker.send_message(message)

    def _on_response(self, answer: str) -> None:
        self.chat_area.append(f"\nALICE: {answer}")
        self.send_button.setEnabled(True)
        self.status_label.setText("Connected")
        if self.speak_replies.isChecked():
            threading.Thread(
                target=self.voice_pipeline.speak, args=(answer,), daemon=True
            ).start()

    def _on_runtime_error(self, message: str) -> None:
        self.chat_area.append(f"\nALICE error: {message}")
        self.send_button.setEnabled(True)
        self.status_label.setText("Needs attention")

    def _show_confirmation(self, message: str, payload: object) -> None:
        approved = QMessageBox.question(
            self, "ALICE permission request", message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes
        payload["approved"] = approved
        payload["event"].set()

    def _activate_voice(self) -> None:
        if not self._voice_recording:
            self._toggle_voice()

    def _toggle_voice(self) -> None:
        if not self._voice_recording:
            if self.runtime_worker and self.runtime_worker.wake_word_enabled:
                self.voice_button.setEnabled(False)
                self.voice_button.setText("Preparing microphone…")
                self.runtime_worker.pause_wake_word()
            else:
                self._begin_voice_recording()
            return

        try:
            self.voice_pipeline.stop_listening()
            self._voice_recording = False
            self.voice_button.setEnabled(False)
            self.voice_button.setText("Transcribing…")
            self._transcription_worker = TranscriptionWorker(self.voice_pipeline, self)
            self._transcription_worker.completed.connect(self._on_transcription)
            self._transcription_worker.failed.connect(self._on_transcription_error)
            self._transcription_worker.finished.connect(self._on_transcription_finished)
            self._transcription_worker.start()
        except Exception as exc:
            self._voice_recording = False
            self.voice_button.setText("🎙  Start voice")
            self.voice_button.setEnabled(True)
            if self.runtime_worker:
                self.runtime_worker.resume_wake_word()
            self._on_runtime_error(f"Could not stop microphone: {exc}")

    def _begin_voice_recording(self) -> None:
        self.voice_button.setEnabled(True)
        try:
            if self.mute_checkbox.isChecked():
                raise RuntimeError("Unmute the microphone in Settings before recording.")
            self.voice_pipeline.start_listening()
            self._voice_recording = True
            self.voice_button.setText("■  Stop & transcribe")
            self.status_label.setText("Listening…")
        except Exception as exc:
            self.voice_button.setText("🎙  Start voice")
            if self.runtime_worker:
                self.runtime_worker.resume_wake_word()
            self._on_runtime_error(f"Could not start microphone: {exc}")

    def _on_transcription_finished(self) -> None:
        self.voice_button.setEnabled(True)
        if self.runtime_worker:
            self.runtime_worker.resume_wake_word()

    def _on_transcription(self, text: str) -> None:
        self.voice_button.setText("🎙  Start voice")
        if not text.strip():
            self._on_runtime_error("No speech was recognized. Please try again.")
            return
        self.chat_input.setPlainText(text.strip())
        self._send_message()

    def _on_transcription_error(self, error: str) -> None:
        self.voice_button.setText("🎙  Start voice")
        self._on_runtime_error(f"Speech recognition failed: {error}")

    def _save_settings(self) -> None:
        try:
            for field, checkbox in self.access_checkboxes.items():
                setattr(self.config.automation, field, checkbox.isChecked())
            self.config.automation.require_confirmation_for_destructive = True
            self.config.voice.mute = self.mute_checkbox.isChecked()
            self.config.voice.wake_word_enabled = self.wakeword_checkbox.isChecked()
            self.config.voice.wake_word = self.wakeword_edit.text().strip() or "alice"
            self.config.voice.microphone_device = self.mic_device_combo.currentData()
            self.config.voice.stt_model = self.stt_model_combo.currentText()
            self.config.voice.voice_activity_detection = self.vad_checkbox.isChecked()
            self.config.voice.tts_engine = "kokoro"
            self.config.voice.tts_language = str(self.tts_language_combo.currentData() or "en-us")
            self.config.voice.tts_voice = str(self.tts_voice_combo.currentData() or "af_heart")
            self.config.voice.tts_rate = self.tts_rate_spin.value()
            self.config.ai.base_url = self.ai_url_edit.text().strip().rstrip("/")
            self.config.ai.model_name = self.model_name_edit.text().strip()
            if not self.config.ai.base_url or not self.config.ai.model_name:
                raise ValueError("LM Studio URL and model name cannot be empty.")
            self.config.startup.start_with_windows = self.startup_checkbox.isChecked()
            self.config.startup.minimize_to_tray = self.tray_checkbox.isChecked()
            from alice.core.startup import set_startup_enabled
            set_startup_enabled(self.startup_checkbox.isChecked())
            shortcut = self.shortcut_edit.text().strip()
            if shortcut:
                self.config.omen.fallback_shortcut = shortcut
            self.config.save()
            QMessageBox.information(
                self, "Settings saved",
                "Settings saved. Restart ALICE to apply microphone and hotkey changes. "
                "Kokoro voice and Silero VAD settings are ready for the next voice request."
            )
        except Exception as exc:
            logger.exception("Could not save ALICE settings")
            QMessageBox.critical(self, "Save failed", str(exc))

    def _update_status(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            self.cpu_label.setText(f"CPU usage: {cpu:.0f}%")
            self.ram_label.setText(f"Memory usage: {ram:.0f}%")
            self.monitor_bar.setValue(int(ram))
        except Exception:
            pass
        if self.orb:
            try:
                self.status_label.setText(f"Assistant: {self.orb.get_status()['state']}")
            except Exception:
                pass

    def _create_tray(self) -> None:
        self.tray_icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(
            self.style().standardIcon(QStyle.SP_ComputerIcon), self
        )
        self.tray_icon.setToolTip("ALICE — Local desktop assistant")
        menu = QMenu(self)
        show_action = QAction("Open ALICE", self)
        show_action.triggered.connect(self._show_from_tray)
        voice_action = QAction("Start voice capture", self)
        voice_action.triggered.connect(self._activate_voice)
        exit_action = QAction("Exit ALICE", self)
        exit_action.triggered.connect(self._exit_application)
        menu.addAction(show_action)
        menu.addAction(voice_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(lambda _reason: self._show_from_tray())
        self.tray_icon.show()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_application(self) -> None:
        self._really_exit = True
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if not self._really_exit and self.config.startup.minimize_to_tray and self.tray_icon:
            self.hide()
            self.tray_icon.showMessage(
                "ALICE is still running",
                "Use the ALICE tray icon to reopen the dashboard or exit.",
                QSystemTrayIcon.Information,
                2500,
            )
            event.ignore()
            return
        if self._voice_recording:
            try:
                self.voice_pipeline.stop_listening()
            except Exception:
                pass
        if self.tray_icon:
            self.tray_icon.hide()
        if self.runtime_worker and self.runtime_worker.isRunning():
            self.runtime_worker.stop()
        super().closeEvent(event)


def run_dashboard(config: Any, orb: Any = None, event_bus: Any = None) -> int:
    """Launch ALICE as a desktop application."""
    from alice.dashboard.runtime_worker import RuntimeWorker

    app = QApplication.instance() or QApplication([])
    worker = RuntimeWorker(config)
    dashboard = Dashboard(config, orb, worker)
    worker.start()
    dashboard.show()
    result = app.exec()
    if worker.isRunning():
        worker.stop()
    return result


if __name__ == "__main__":
    from alice.core.config import Config
    run_dashboard(Config.load())
