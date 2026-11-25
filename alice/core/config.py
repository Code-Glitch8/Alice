#!/usr/bin/env python3
"""Configuration management for ALICE."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict


def default_alice_home() -> Path:
    configured = os.getenv("ALICE_HOME")
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    if os.name == "nt":
        return Path(os.getenv("ALICE_HOME", r"D:\Alice"))
    return Path.home() / ".alice"


@dataclass
class AIConfig:
    runtime: str = "lmstudio"
    # LM Studio returns the authoritative model key via GET /api/v1/models.
    # This fuzzy label selects the downloaded Qwen 3.5 4B model when present.
    model_name: str = "qwen3.5-4b"
    model_path: str = ""
    base_url: str = "http://127.0.0.1:1234"
    api_token: str = ""
    lms_cli: str = ""
    auto_start_server: bool = True
    startup_timeout: int = 30
    request_timeout: int = 180
    context_length: int = 8192
    gpu_layers: int = -1
    cpu_offload: bool = True
    idle_timeout: int = 300
    auto_load: bool = False
    auto_start_runtime: bool = True
    temperature: float = 0.7
    max_tokens: int = 3072


@dataclass
class VoiceConfig:
    wake_word: str = "alice"
    wake_word_enabled: bool = True
    stt_engine: str = "faster-whisper"
    stt_model: str = "base"
    tts_engine: str = "piper"
    tts_voice: str = "default"
    tts_rate: int = 150
    microphone_device: Optional[int] = None
    mute: bool = False
    voice_activity_detection: bool = True


@dataclass
class AutomationConfig:
    auto_confirm_category_a: bool = True
    require_confirm_category_b: bool = True
    restricted_category_c: bool = True
    emergency_stop_enabled: bool = True
    allowed_locations: list = field(default_factory=lambda: [
        str(Path.home() / "Desktop"),
        str(Path.home() / "Documents"),
        str(Path.home() / "Downloads"),
    ])


@dataclass
class BrowserConfig:
    enabled: bool = True
    browser: str = "chrome"
    headless: bool = False
    user_data_dir: str = ""
    search_engine: str = "google"


@dataclass
class OrbConfig:
    enabled: bool = True
    size: int = 80
    opacity: float = 0.9
    position_x: int = 100
    position_y: int = 100
    draggable: bool = True
    always_on_top: bool = True


@dataclass
class OmenConfig:
    enabled: bool = True
    event_id: Optional[int] = None
    event_data: Optional[int] = None
    suppress_default_launch: bool = False
    fallback_shortcut: str = "ctrl+alt+a"
    diagnostic_mode: bool = False


@dataclass
class StartupConfig:
    start_with_windows: bool = False
    start_minimized: bool = True
    open_dashboard: bool = False
    background_service: bool = True


@dataclass
class PrivacyConfig:
    no_telemetry: bool = True
    local_only: bool = True
    save_conversations: bool = True
    save_memory: bool = True
    temporary_audio_only: bool = True


@dataclass
class Config:
    ai: AIConfig = field(default_factory=AIConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    orb: OrbConfig = field(default_factory=OrbConfig)
    omen: OmenConfig = field(default_factory=OmenConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    data_dir: str = field(default_factory=lambda: str(default_alice_home()))

    @classmethod
    def default_config_path(cls) -> Path:
        return default_alice_home() / "config" / "config.json"

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Config":
        path = Path(path or os.getenv("ALICE_CONFIG", cls.default_config_path()))
        if not path.exists():
            config = cls()
            # Existing deployments may have ALICE_HOME set to D:\\Alice.
            config.data_dir = str(default_alice_home())
            return config
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("Configuration root must be a JSON object")
            return cls._from_dict(data)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"Warning: Failed to load config {path}: {exc}. Using defaults.")
            return cls()

    def save(self, path: Optional[str | Path] = None) -> None:
        target = Path(path or self.default_config_path())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self._to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "ai": asdict(self.ai), "voice": asdict(self.voice),
            "automation": asdict(self.automation), "browser": asdict(self.browser),
            "orb": asdict(self.orb), "omen": asdict(self.omen),
            "startup": asdict(self.startup), "privacy": asdict(self.privacy),
            "data_dir": self.data_dir,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "Config":
        config = cls()
        for section in ("ai", "voice", "automation", "browser", "orb", "omen", "startup", "privacy"):
            section_data = data.get(section)
            if isinstance(section_data, dict):
                target = getattr(config, section)
                for key, value in section_data.items():
                    if hasattr(target, key):
                        setattr(target, key, value)
        if isinstance(data.get("data_dir"), str) and data["data_dir"].strip():
            config.data_dir = data["data_dir"]
        return config
