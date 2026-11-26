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


def get_windows_known_folder_path(folder_id: str) -> Optional[Path]:
    """Get a Windows known folder path using SHGetKnownFolderPath API.

    This is more reliable than hardcoded paths like Path.home() / "Desktop".

    Args:
        folder_id: KNOWNFOLDERID string (e.g., "FOLDERID_Desktop", "FOLDERID_Downloads")

    Returns:
        Path to the known folder, or None if not found
    """
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes
        from uuid import UUID

        # GUID mapping for common folders
        folder_guids = {
            "FOLDERID_Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
            "FOLDERID_Documents": "{FDD39AD8-70D2-4664-B824-9D18820A6B39}",
            "FOLDERID_Downloads": "{338E6FE1-3C68-4A47-B188-7540A5DD143}",
            "FOLDERID_AppData_Roaming": "{FC4781D-32FE-40D6-BFE3-8FB749A51591}",
            "FOLDERID_AppData_Local": "{C0698386-5A63-40AC-B948-E3115505689F}",
            "FOLDERID_AppData_Local_Machine": "{62598461-039D-474B-9415-5602349A3313}",
        }

        guid_str = folder_guids.get(folder_id)
        if not guid_str:
            return None

        # Parse the GUID string and create a properly formatted GUID structure
        guid_obj = UUID(guid_str)

        # Create GUID with correct byte ordering for Windows API
        # The UUID module handles the conversion properly
        guid = wintypes.GUID()
        guid.Data1 = guid_obj.time_low
        guid.Data2 = guid_obj.time_mid
        guid.Data3 = guid_obj.time_hi_version
        guid.Data4[0] = guid_obj.clock_seq_hi_variant
        guid.Data4[1] = guid_obj.clock_seq_low
        # Copy the node (bytes 8-13)
        for i in range(6):
            guid.Data4[2 + i] = guid_obj.node[i]

        # Call SHGetKnownFolderPath with correct parameters
        buffer = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, buffer
        )

        if result == 0:
            return Path(buffer.value)
    except Exception:
        pass

    return None


def get_windows_known_folder(folder_name: str) -> Optional[Path]:
    """Get Windows known folder path by friendly name.

    Args:
        folder_name: Name of the folder ("Desktop", "Documents", "Downloads")

    Returns:
        Path to the folder, or None if not found
    """
    folder_map = {
        "Desktop": "FOLDERID_Desktop",
        "Documents": "FOLDERID_Documents",
        "Downloads": "FOLDERID_Downloads",
    }

    folder_id = folder_map.get(folder_name)
    if not folder_id:
        return None

    path = get_windows_known_folder_path(folder_id)
    return path


def resolve_allowed_locations() -> list:
    """Resolve the default allowed locations for file operations.

    Uses Windows known folder APIs when available for reliable path resolution.
    Falls back to Path.home() based paths on non-Windows systems.
    """
    locations = []

    if os.name == "nt":
        # Windows: use known folder API for reliability
        for folder_name in ["Desktop", "Documents", "Downloads"]:
            path = get_windows_known_folder(folder_name)
            if path:
                locations.append(str(path))

        # If API failed, fall back to environment variables
        if not locations:
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                for folder in ["Desktop", "Documents", "Downloads"]:
                    p = Path(user_profile) / folder
                    if p.exists():
                        locations.append(str(p))
    else:
        # Non-Windows: use home directory
        for folder in ["Desktop", "Documents", "Downloads"]:
            p = Path.home() / folder
            if p.exists():
                locations.append(str(p))

    # Ensure we always have at least the default locations
    if not locations:
        if os.name == "nt":
            user_profile = os.environ.get("USERPROFILE", Path.home())
            locations = [
                str(Path(user_profile) / "Desktop"),
                str(Path(user_profile) / "Documents"),
                str(Path(user_profile) / "Downloads"),
            ]
        else:
            locations = [
                str(Path.home() / "Desktop"),
                str(Path.home() / "Documents"),
                str(Path.home() / "Downloads"),
            ]

    return locations


@dataclass
class AutomationConfig:
    auto_confirm_category_a: bool = True
    require_confirm_category_b: bool = False  # Set to False to auto-confirm Category B actions
    restricted_category_c: bool = True
    emergency_stop_enabled: bool = True
    allowed_locations: list = field(default_factory=resolve_allowed_locations)


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
