#!/usr/bin/env python3
"""
Computer Control Engine for ALICE.
Provides file operations, application control, and system information.
"""

import logging
import subprocess
import os
import time
import psutil
import winreg
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ComputerEngine:
    """Local computer control engine for ALICE."""

    # Known application aliases and their executable paths/commands
    APP_ALIASES = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "vs code": "code.exe",
        "vscode": "code.exe",
        "visual studio code": "code.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "paint": "mspaint.exe",
        "wordpad": "write.exe",
        "snipping tool": "snippingtool.exe",
        "control panel": "control.exe",
        "device manager": "devmgmt.msc",
        "disk management": "diskmgmt.msc",
        "registry editor": "regedit.exe",
        "services": "services.msc",
    }

    def __init__(self, config: Any = None):
        self.config = config
        self.running_apps: List[Dict[str, Any]] = []
        self._app_owner = None
        if config:
            try:
                from alice.core.application_owner import ApplicationOwner
                self._app_owner = ApplicationOwner.get_instance()
            except Exception:
                self._app_owner = None

    # File operations
    def search_files(self, query: str, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for files by name or extension."""
        from alice.computer.file_operations import FileOperations
        from alice.core.config import Config

        config = Config.load()
        fo = FileOperations(config)
        return fo.search_files(query, folder)

    def create_folder(self, path: str) -> Tuple[bool, str]:
        """Create a folder at the specified path. Returns (success, message).

        Verifies that the folder actually exists after creation.
        """
        try:
            folder = Path(path).resolve()
            folder.mkdir(parents=True, exist_ok=True)

            # Verify the folder exists
            if folder.exists() and folder.is_dir():
                return True, f"Created folder: {path}"
            else:
                return False, f"Folder creation failed - folder not found at {path}"
        except Exception as e:
            logger.error(f"Failed to create folder {path}: {e}")
            return False, str(e)

    def extract_zip(self, archive_path: str, destination: Optional[str] = None) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Extract a ZIP archive. Returns (success, message, extracted_files)."""
        import zipfile
        results = []
        try:
            archive = Path(archive_path)
            if not archive.exists():
                return False, f"Archive not found: {archive_path}", results

            if destination:
                dest_path = Path(destination)
            else:
                dest_path = archive.parent

            dest_path.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(str(archive), 'r') as zf:
                names = zf.namelist()
                zf.extractall(str(dest_path))
                for name in names:
                    extracted_path = dest_path / name
                    if extracted_path.exists():
                        results.append({
                            "name": name,
                            "path": str(extracted_path),
                            "size": extracted_path.stat().st_size if extracted_path.is_file() else 0,
                        })

            return True, f"Extracted {len(results)} files from {archive_path}", results
        except Exception as e:
            logger.error(f"Failed to extract ZIP {archive_path}: {e}")
            return False, str(e), results

    # Application control
    def _resolve_app(self, app_name: str, target_path: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Resolve an application name to an executable command and its type.

        Uses multiple discovery methods:
        1. Known aliases (hardcoded common apps)
        2. PATH environment variable
        3. Windows registry App Paths
        4. Start Menu shortcuts (roaming and all-users)
        5. UWP/MSIX packaged applications

        Returns (command, type) where type is 'exe', 'protocol', 'msc', or 'explorer'.
        For File Explorer, can optionally specify a target path.
        """
        app_lower = app_name.lower().strip()

        # Check known aliases
        if app_lower in self.APP_ALIASES:
            cmd = self.APP_ALIASES[app_lower]
            if cmd.endswith(".msc"):
                return cmd, "msc"
            elif cmd.endswith(":"):
                return cmd, "protocol"
            elif cmd == "explorer.exe":
                # Special handling for File Explorer - can open a specific folder
                if target_path:
                    return f'explorer.exe "{target_path}"', "explorer"
                return cmd, "explorer"
            return cmd, "exe"

        # Handle File Explorer variations
        if "explorer" in app_lower or ("file" in app_lower and "explorer" in app_lower):
            if target_path:
                return f'explorer.exe "{target_path}"', "explorer"
            return "explorer.exe", "explorer"

        # Try to find in PATH
        try:
            result = subprocess.run(
                ["where", app_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                return path, "exe"
        except Exception:
            pass

        # Try registry for installed applications
        try:
            # Check common registry locations for installed apps
            reg_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
            ]
            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                if app_lower in subkey_name.lower():
                                    with winreg.OpenKey(key, subkey_name) as subkey:
                                        path, _ = winreg.QueryValueEx(subkey, "")
                                        if path and Path(path).exists():
                                            return path, "exe"
                                i += 1
                            except OSError:
                                break
                except OSError:
                    continue
        except Exception:
            pass

        # Discover from Start Menu shortcuts (roaming and local)
        try:
            start_menu_paths = self._get_start_menu_paths()
            for menu_path in start_menu_paths:
                exe_path = self._find_app_in_start_menu(menu_path, app_lower)
                if exe_path:
                    return exe_path, "exe"
        except Exception:
            pass

        # Try to find UWP/MSIX packaged applications
        try:
            uwp_command = self._find_uwp_app(app_lower)
            if uwp_command:
                command_type = "protocol" if uwp_command.startswith(("shell:", "ms-", "calculator:")) else "exe"
                return uwp_command, command_type
        except Exception:
            pass

        return None, None

    def _get_start_menu_paths(self) -> List[Path]:
        """Get common Start Menu shortcut locations on Windows."""
        paths = []
        try:
            # User's Start Menu
            appdata = os.environ.get("APPDATA")
            if appdata:
                user_start = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                if user_start.exists():
                    paths.append(user_start)

            # All Users Start Menu
            program_data = os.environ.get("PROGRAMDATA") or "C:\\ProgramData"
            all_users_start = Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if all_users_start.exists():
                paths.append(all_users_start)

            # Check for Start Menu folder variants
            start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu"
            if start_menu.exists():
                paths.append(start_menu / "Programs")
        except Exception:
            pass
        return paths

    def _find_app_in_start_menu(self, menu_path: Path, app_name: str) -> Optional[str]:
        """Search for an application shortcut in a Start Menu folder."""
        try:
            # Search through all subdirectories for .lnk or .exe shortcuts
            for root, dirs, files in os.walk(menu_path):
                for filename in files:
                    filepath = Path(root) / filename
                    if filename.lower().endswith('.lnk'):
                        # Check if the shortcut filename contains our app name
                        if app_name in filename.replace('.lnk', '').lower():
                            # Get the target of the shortcut via COM
                            try:
                                import pythoncom
                                from win32com.shell import shell
                                shortcut = shell.CreateShortCut(str(filepath))
                                if shortcut and Path(shortcut.Targetpath).exists():
                                    return shortcut.Targetpath
                            except Exception:
                                pass
                    elif filename.lower().endswith('.exe') and app_name in filename.lower():
                        if filepath.exists():
                            return str(filepath)
        except Exception:
            pass
        return None

    def _find_uwp_app(self, app_name: str) -> Optional[str]:
        """Resolve a packaged Windows app to a launchable URI or executable.

        Return a single string. The previous implementation sometimes returned
        (command, type) here, which _resolve_app wrapped again and passed to
        subprocess as a tuple, producing the reported path-like-object error.
        """
        normalized = app_name.lower().strip()
        packaged_aliases = {
            "microsoft store": "ms-windows-store:",
            "store": "ms-windows-store:",
            "calculator": "calculator:",
            "calc": "calculator:",
        }
        if normalized in packaged_aliases:
            return packaged_aliases[normalized]

        # Use the AppsFolder shell namespace for MSIX/UWP apps. Match the
        # package's display name and return its AppUserModelID as a shell URI.
        try:
            command = (
                "$ErrorActionPreference='Stop'; "
                "$apps=Get-StartApps; "
                "$match=$apps | Where-Object { $_.Name -like '*"
                + normalized.replace("'", "''")
                + "*' } | Select-Object -First 1; "
                "if ($match) { $match.AppID }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            app_id = (result.stdout or "").strip()
            if result.returncode == 0 and app_id:
                return "shell:AppsFolder\\" + app_id
        except Exception as exc:
            logger.debug("Packaged app discovery failed for %s: %s", app_name, exc)
        return None

    def open_app(self, app_name: str, target_path: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Open an application by name. Returns (success, message, details).

        For File Explorer, can optionally specify target_path to open a specific folder.
        """
        logger.info(f"Opening application: {app_name} (target: {target_path})")

        command, cmd_type = self._resolve_app(app_name, target_path)
        if not command:
            return False, f"Application not found: {app_name}", {"app": app_name, "error": "not_found"}

        try:
            process = None
            if cmd_type == "protocol":
                # Handle URI protocols like ms-settings:
                process = subprocess.Popen(["cmd", "/c", "start", "", command], shell=False)
            elif cmd_type == "msc":
                # Handle MMC snap-ins
                process = subprocess.Popen(["mmc", command], shell=False)
            elif cmd_type == "explorer":
                # Handle File Explorer - use direct shell execution
                process = subprocess.Popen(command, shell=True)
            else:
                # Regular executable
                # For UWP apps like Notepad, use start command to launch properly
                process = subprocess.Popen(["cmd", "/c", "start", "", command], shell=False)

            # Wait briefly to verify process started
            time.sleep(1.0)

            # Check if process is still running OR if it's a UWP app that spawned a child
            if process.poll() is not None:
                # Process exited - could be a UWP app that launched a child process
                # Try to find the actual running process by name
                app_lower = app_name.lower()
                time.sleep(0.5)  # Give child process time to start
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        proc_name = proc.info['name'] or ""
                        if app_lower in proc_name.lower():
                            details = {
                                "app": app_name,
                                "command": command,
                                "pid": proc.info['pid'],
                                "name": proc_name,
                                "status": "running"
                            }
                            self.running_apps.append(details)
                            # Register with ApplicationOwner if available
                            if self._app_owner:
                                self._app_owner.register_app(app_name, proc.info['pid'])
                            return True, f"Opened {app_name} (PID: {proc.info['pid']})", details
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return False, f"Application failed to start: {app_name} (exit code: {process.returncode})", {
                    "app": app_name,
                    "command": command,
                    "error": "process_exited",
                    "exit_code": process.returncode
                }

            # Get process info
            try:
                ps_process = psutil.Process(process.pid)
                details = {
                    "app": app_name,
                    "command": command,
                    "pid": process.pid,
                    "name": ps_process.name(),
                    "status": "running"
                }
                self.running_apps.append(details)
                # Register with ApplicationOwner if available
                if self._app_owner:
                    self._app_owner.register_app(app_name, process.pid)
                return True, f"Opened {app_name} (PID: {process.pid})", details
            except psutil.NoSuchProcess:
                return False, f"Process died immediately: {app_name}", {"app": app_name, "error": "process_died"}

        except FileNotFoundError:
            return False, f"Executable not found: {command}", {"app": app_name, "command": command, "error": "file_not_found"}
        except Exception as e:
            logger.error(f"Failed to open {app_name}: {e}")
            return False, f"Failed to open {app_name}: {e}", {"app": app_name, "error": str(e)}

    def close_app(self, app_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Close an application by name. Returns (success, message, details)."""
        logger.info(f"Closing application: {app_name}")

        app_lower = app_name.lower().strip()
        closed_count = 0
        errors = []

        # Find and terminate matching processes
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_name = proc.info['name'] or ""
                proc_exe = proc.info['exe'] or ""

                if (app_lower in proc_name.lower() or
                    (proc_exe and app_lower in Path(proc_exe).stem.lower())):
                    proc.terminate()
                    closed_count += 1
                    # Remove from running_apps
                    self.running_apps = [a for a in self.running_apps if a.get('pid') != proc.info['pid']]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                errors.append(str(e))

        if closed_count > 0:
            return True, f"Closed {closed_count} process(es) for {app_name}", {"closed": closed_count, "errors": errors}
        else:
            return False, f"No running processes found for {app_name}", {"app": app_name, "errors": errors}

    def focus_app(self, app_name: str) -> Tuple[bool, str]:
        """Bring an application window to the foreground."""
        try:
            import pywinauto
            from pywinauto import Desktop

            windows = Desktop(backend="uia").windows()
            app_lower = app_name.lower()

            for window in windows:
                try:
                    if (app_lower in window.window_text().lower() or
                        app_lower in (window.class_name() or "").lower()):
                        window.set_focus()
                        return True, f"Focused window: {window.window_text()}"
                except Exception:
                    continue

            return False, f"No window found for {app_name}"
        except ImportError:
            return False, "pywinauto not available"
        except Exception as e:
            return False, f"Failed to focus {app_name}: {e}"

    def auto_focus_most_relevant(self) -> bool:
        """Focus the most recently opened application or the most relevant window.

        This method finds the most appropriate target window for text input.
        Priority:
        1. Recently opened applications by ALICE
        2. Windows with ALICE in the title (if any)
        3. The currently active/focused window

        Returns:
            True if a window was successfully focused, False otherwise
        """
        try:
            import pywinauto
            from pywinauto import Desktop
            from alice.core.application_owner import ApplicationOwner

            # First, check ALICE's owned applications
            owner = ApplicationOwner.get_instance()
            owned_apps = owner.get_owned_apps()

            if owned_apps:
                # Find the most recently opened owned app that's still running
                for app_record in reversed(owned_apps):
                    app_name = app_record.get("app")
                    try:
                        windows = Desktop(backend="uia").windows()
                        for window in windows:
                            try:
                                window_text = window.window_text().lower()
                                class_name = (window.class_name() or "").lower()
                                if app_name.lower() in window_text or app_name.lower() in class_name:
                                    window.set_focus()
                                    logger.debug(f"Auto-focused ALICE-owned app: {app_name}")
                                    return True
                            except Exception:
                                continue
                    except Exception:
                        continue

            # Try to focus windows that might be relevant for typing
            # Look for windows with common editor names
            editor_names = ["notepad", "word", "wordpad", "paint", "code", "visual studio",
                           "document", "text", "editor", "chrome", "firefox", "edge"]

            try:
                windows = Desktop(backend="uia").windows()
                for window in windows:
                    try:
                        window_text = window.window_text().lower()
                        # Skip invisible or minimized windows
                        if not window.is_visible():
                            continue
                        # Check for editor-related windows
                        for editor in editor_names:
                            if editor in window_text:
                                window.set_focus()
                                logger.debug(f"Auto-focused editor window: {window.window_text()}")
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

            # Fall back to getting the active window
            try:
                desktop = Desktop(backend="uia")
                # Get the top-level windows and try to set focus to the active one
                windows = desktop.windows()
                if windows:
                    # Try to focus the first visible window (likely the most recently active)
                    for window in windows:
                        try:
                            if window.is_visible() and window.is_enabled():
                                window.set_focus()
                                logger.debug(f"Auto-focused active window: {window.window_text()}")
                                return True
                        except Exception:
                            continue
            except Exception:
                pass

            return False
        except ImportError:
            logger.warning("pywinauto not available for auto-focus")
            return False
        except Exception as e:
            logger.debug(f"Auto-focus failed: {e}")
            return False

    def list_installed_apps(self) -> List[Dict[str, Any]]:
        """Discover and list installed applications on the system.

        Uses multiple discovery methods:
        1. Windows registry App Paths and Uninstall entries
        2. Start Menu shortcuts
        3. PATH environment variable

        Returns:
            List of installed applications with name, path, and type
        """
        apps = []
        seen_names = set()

        # Method 1: Check registry for installed applications
        try:
            import winreg

            # Check App Paths
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]

            for root, reg_path in reg_paths:
                try:
                    with winreg.OpenKey(root, reg_path) as key:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    # Try to get display name
                                    try:
                                        display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                        install_location, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                        install_string, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                    except (FileNotFoundError, OSError):
                                        display_name = subkey_name
                                        install_location = ""
                                        install_string = ""

                                    # Try to get executable path
                                    try:
                                        exe_path, _ = winreg.QueryValueEx(subkey, "")
                                        if exe_path and Path(exe_path).exists():
                                            app_key = display_name.lower().strip() if display_name else subkey_name.lower()
                                            if app_key not in seen_names:
                                                seen_names.add(app_key)
                                                apps.append({
                                                    "name": display_name or subkey_name,
                                                    "path": exe_path,
                                                    "type": "registry",
                                                    "install_location": install_location
                                                })
                                    except (FileNotFoundError, OSError):
                                        pass

                                i += 1
                            except OSError:
                                break
                except OSError:
                    continue
        except Exception as e:
            logger.debug(f"Registry discovery error: {e}")

        # Method 2: Check Start Menu shortcuts
        try:
            start_menu_paths = self._get_start_menu_paths()
            for menu_path in start_menu_paths:
                if not menu_path.exists():
                    continue
                for root, dirs, files in os.walk(menu_path):
                    for filename in files:
                        if filename.lower().endswith('.lnk'):
                            filepath = Path(root) / filename
                            app_name = filename.replace('.lnk', '').strip()
                            if app_name not in seen_names:
                                try:
                                    import pythoncom
                                    from win32com.shell import shell
                                    shortcut = shell.CreateShortCut(str(filepath))
                                    if shortcut and shortcut.Targetpath:
                                        seen_names.add(app_name.lower())
                                        apps.append({
                                            "name": app_name,
                                            "path": shortcut.Targetpath,
                                            "type": "start_menu",
                                            "shortcut": str(filepath)
                                        })
                                except Exception:
                                    pass
        except Exception as e:
            logger.debug(f"Start Menu discovery error: {e}")

        # Method 3: Add known aliases
        for alias, exe in self.APP_ALIASES.items():
            alias_lower = alias.lower()
            if alias_lower not in seen_names:
                seen_names.add(alias_lower)
                apps.append({
                    "name": alias,
                    "path": exe,
                    "type": "alias"
                })

        # Method 4: Check PATH for executables
        try:
            path_dirs = os.environ.get("PATH", "").split(";")
            for path_dir in path_dirs[:50]:  # Limit to prevent performance issues
                path_dir = Path(path_dir)
                if not path_dir.exists() or not path_dir.is_dir():
                    continue
                for exe_file in list(path_dir.glob("*.exe"))[:10]:  # Limit per directory
                    app_name = exe_file.stem
                    if app_name.lower() not in seen_names:
                        seen_names.add(app_name.lower())
                        apps.append({
                            "name": app_name,
                            "path": str(exe_file),
                            "type": "path"
                        })
        except Exception:
            pass

        return apps

    def find_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Find an installed application by name.

        Args:
            app_name: The application name to search for

        Returns:
            Dictionary with app info or None if not found
        """
        app_lower = app_name.lower().strip()

        # Check known aliases first
        if app_lower in self.APP_ALIASES:
            return {
                "name": app_name,
                "path": self.APP_ALIASES[app_lower],
                "type": "alias"
            }

        # Check running apps first
        for app in self.running_apps:
            if app_lower in app.get("name", "").lower():
                return {
                    "name": app.get("name"),
                    "path": app.get("command", ""),
                    "type": "running",
                    "pid": app.get("pid")
                }

        # Check registry
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
            ]

            for root, reg_path in reg_paths:
                try:
                    with winreg.OpenKey(root, reg_path) as key:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                if app_lower in subkey_name.lower():
                                    with winreg.OpenKey(key, subkey_name) as subkey:
                                        exe_path, _ = winreg.QueryValueEx(subkey, "")
                                        if exe_path and Path(exe_path).exists():
                                            return {
                                                "name": subkey_name,
                                                "path": exe_path,
                                                "type": "registry"
                                            }
                                i += 1
                            except OSError:
                                break
                except OSError:
                    continue
        except Exception:
            pass

        # Search Start Menu
        try:
            start_menu_paths = self._get_start_menu_paths()
            for menu_path in start_menu_paths:
                if not menu_path.exists():
                    continue
                result = self._find_app_in_start_menu(menu_path, app_lower)
                if result:
                    return {
                        "name": app_name,
                        "path": result,
                        "type": "start_menu"
                    }
        except Exception:
            pass

        return None

    def get_running_apps(self) -> List[Dict[str, Any]]:
        """Get list of currently running applications."""
        apps = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['name']:
                    apps.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "exe": info['exe'],
                        "cpu_percent": info['cpu_percent'],
                        "memory_percent": info['memory_percent']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return apps

    # System information
    def get_system_info(self) -> Dict[str, Any]:
        """Get CPU, RAM, GPU usage information."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory()
            return {
                "cpu_percent": cpu,
                "ram_percent": ram.percent,
                "ram_used_gb": round(ram.used / (1024**3), 2),
                "ram_total_gb": round(ram.total / (1024**3), 2),
                "gpu_percent": 0.0,
                "vram_mb": 0.0,
            }
        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return {
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_used_gb": 0.0,
                "ram_total_gb": 0.0,
                "gpu_percent": 0.0,
                "vram_mb": 0.0,
            }

    # Browser control
    def open_browser(self, url: str, search: Optional[str] = None) -> Tuple[bool, str]:
        """Open browser and optionally search."""
        try:
            if search and not url:
                import urllib.parse
                query = urllib.parse.quote(search)
                url = f"https://www.google.com/search?q={query}"

            # Try to use default browser
            import webbrowser
            webbrowser.open(url)
            return True, f"Opened browser: {url}"
        except Exception as e:
            logger.error(f"Open browser error: {e}")
            return False, str(e)

    # Status
    def get_status(self) -> Dict[str, Any]:
        """Get computer engine status."""
        return {
            "running_apps": self.running_apps,
            "operation_active": False,
        }


if __name__ == "__main__":
    # Standalone test
    engine = ComputerEngine(None)
    print("ComputerEngine initialized")
    print(engine.get_status())
    print("\n--- Testing Notepad ---")
    success, msg, details = engine.open_app("notepad")
    print(f"Result: {success} - {msg}")
    print(f"Details: {details}")