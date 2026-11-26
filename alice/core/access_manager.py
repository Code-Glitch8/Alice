"""Centralized local computer-access policy and Windows drive discovery.

ALICE never elevates itself. Operations are limited to paths the current
Windows account can access; this module only discovers drives and enforces
the user's configured permissions.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any


def discover_drive_roots() -> list[Path]:
    """Return mounted filesystem roots without requesting elevation."""
    roots: list[Path] = []
    if os.name == "nt":
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for index in range(26):
                if mask & (1 << index):
                    root = Path(f"{chr(65 + index)}:\\")
                    if root.exists():
                        roots.append(root)
        except Exception:
            pass
    else:
        roots.append(Path.home())
    return roots


def _resolved(path: str | Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    return Path(expanded).resolve(strict=False)


def is_within(path: str | Path, root: str | Path) -> bool:
    """Use path-component containment, not unsafe string-prefix matching."""
    try:
        candidate = _resolved(path)
        base = _resolved(root)
        return os.path.commonpath([str(candidate), str(base)]).casefold() == str(base).casefold()
    except (OSError, ValueError, RuntimeError):
        return False


class ComputerAccessManager:
    """Read the live config and make allow/deny decisions for computer tools."""

    def __init__(self, config: Any):
        self.config = config
        self.settings = getattr(config, "automation", config)

    def roots(self) -> list[Path]:
        configured = list(getattr(self.settings, "allowed_locations", []) or [])
        if getattr(self.settings, "search_all_drives", True):
            candidates = discover_drive_roots() + [Path.cwd()]
        else:
            candidates = [Path(p) for p in configured] + [Path.cwd()]
        roots: list[Path] = []
        for item in candidates:
            try:
                resolved = _resolved(item)
                if resolved.exists() and resolved not in roots:
                    roots.append(resolved)
            except (OSError, RuntimeError):
                continue
        return roots

    def path_allowed(self, path: str | Path) -> bool:
        return any(is_within(path, root) for root in self.roots())

    def permission_enabled(self, action: str) -> bool:
        mapping = {
            # Turning off all-drive discovery narrows search to configured
            # folders; it does not disable ordinary file search.
            "search_files": "allow_read_files",
            "list_drives": "search_all_drives",
            "read_file": "allow_read_files",
            "create_folder": "allow_create_files_folders",
            "move_file": "allow_move_files",
            "rename_file": "allow_move_files",
            "delete_file": "allow_delete_files",
            "delete_folder": "allow_delete_files",
            "open_app": "allow_app_control",
            "close_app": "allow_app_control",
            "focus_app": "allow_app_control",
            "browser_open": "allow_app_control",
            "browser_extract": "allow_app_control",
            "browser_download": "allow_app_control",
            "browser_screenshot": "allow_app_control",
            "close_all_apps": "allow_app_control",
            "get_open_apps": "allow_app_control",
            "get_app_status": "allow_app_control",
            "list_installed_apps": "allow_app_control",
            "list_running_apps": "allow_app_control",
            "type_text": "allow_app_control",
            "keyboard_shortcut": "allow_app_control",
            "mouse_move": "allow_app_control",
            "mouse_click": "allow_app_control",
            "mouse_scroll": "allow_app_control",
            "select_text": "allow_app_control",
            "copy_paste": "allow_app_control",
        }
        if action == "write_file":
            return bool(
                getattr(self.settings, "allow_create_files_folders", True)
                or getattr(self.settings, "allow_edit_files", True)
            )
        field = mapping.get(action)
        return bool(getattr(self.settings, field, True)) if field else True

    def validate_path(self, path: str | Path) -> tuple[bool, str]:
        if not self.path_allowed(path):
            return False, f"Path is outside ALICE's enabled computer-access scope: {path}"
        return True, ""

    def protected_destructive_path(self, path: str | Path) -> bool:
        """Never recursively delete or move critical Windows installation roots."""
        candidate = _resolved(path)
        protected = []
        if os.name == "nt":
            system_root = Path(os.environ.get("WINDIR", r"C:\Windows"))
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            protected.extend([system_root, program_files, program_files_x86, program_data])
        # A drive root itself is never a valid destructive target.
        if candidate == Path(candidate.anchor):
            return True
        return any(is_within(candidate, item) for item in protected)

    def status(self) -> dict:
        roots = self.roots()
        return {
            "search_all_drives": bool(getattr(self.settings, "search_all_drives", True)),
            "discovered_drives": [str(root) for root in discover_drive_roots()],
            "access_roots": [str(root) for root in roots],
            "permissions": {
                "read_files": bool(getattr(self.settings, "allow_read_files", True)),
                "create_files_folders": bool(getattr(self.settings, "allow_create_files_folders", True)),
                "edit_files": bool(getattr(self.settings, "allow_edit_files", True)),
                "move_and_organize": bool(getattr(self.settings, "allow_move_files", True)),
                "control_applications": bool(getattr(self.settings, "allow_app_control", True)),
                "delete_files": bool(getattr(self.settings, "allow_delete_files", True)),
                "confirm_destructive_actions": True,
            },
            "elevation": "not_requested",
        }
