#!/usr/bin/env python3
"""
Registered tools for ALICE's task executor.
Provides structured tools for file operations, app control, browser automation.
"""

import logging
import asyncio
import json
import os
import shutil
import subprocess
import time
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools for the task executor."""

    def __init__(self):
        self.tools: dict = {}

    def register(self, tool):
        """Register a tool."""
        self.tools[tool.name] = tool
        return tool

    def get(self, name: str):
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> list:
        """List all registered tools."""
        return list(self.tools.values())

    def get_tool(self, name: str):
        """Alias for get() for compatibility."""
        return self.get(name)


class Tool:
    """Base tool class."""

    def __init__(self, name: str, description: str, required_permission: str = "A"):
        self.name = name
        self.description = description
        self.required_permission = required_permission

    def execute(self, **kwargs) -> dict:
        """Execute the tool."""
        raise NotImplementedError


# Specific tool implementations


class OpenAppTool(Tool):
    """Open an application."""

    def __init__(self):
        super().__init__("open_app", "Open an application", required_permission="A")

    def execute(self, **kwargs) -> dict:
        # Support both 'app_name' and 'app' parameter names for flexibility
        app_name = kwargs.get("app_name") or kwargs.get("app")
        target_path = kwargs.get("target_path") or kwargs.get("path") or kwargs.get("folder")

        if not app_name:
            return {
                "status": "error",
                "action": "open_app",
                "app": None,
                "message": "Missing required parameter: app_name or app",
                "result": None,
                "verification": {"process_running": False},
                "error": "Missing required parameter: app_name or app"
            }
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            success, message, details = engine.open_app(app_name, target_path)
            return {
                "status": "success" if success else "error",
                "action": "open_app",
                "app": app_name,
                "target_path": target_path,
                "message": message,
                "result": details if success else None,
                "verification": {
                    "process_running": success,
                    "pid": details.get("pid") if success else None
                },
                "error": None if success else message
            }
        except Exception as e:
            logger.error(f"OpenAppTool error: {e}")
            return {
                "status": "error",
                "action": "open_app",
                "app": app_name,
                "message": str(e),
                "result": None,
                "verification": {"process_running": False},
                "error": str(e)
            }


class CloseAppTool(Tool):
    """Close an application."""

    def __init__(self):
        super().__init__("close_app", "Close an application", required_permission="B")

    def execute(self, **kwargs) -> dict:
        # Support both 'app_name' and 'app' parameter names for flexibility
        app_name = kwargs.get("app_name") or kwargs.get("app")
        if not app_name:
            return {
                "status": "error",
                "action": "close_app",
                "app": None,
                "message": "Missing required parameter: app_name or app",
                "result": None,
                "verification": {"processes_closed": 0},
                "error": "Missing required parameter: app_name or app"
            }
        # Chrome launched by ALICE uses a dedicated persistent profile. Never
        # terminate the user's unrelated default-profile Chrome windows.
        if str(app_name).strip().lower() in {"chrome", "google chrome"}:
            return BrowserOpenTool.close_owned_browser()

        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            success, message, details = engine.close_app(app_name)
            return {
                "status": "success" if success else "error",
                "action": "close_app",
                "app": app_name,
                "message": message,
                "result": details if success else None,
                "verification": {
                    "processes_closed": details.get("closed", 0) if success else 0
                },
                "error": None if success else message
            }
        except Exception as e:
            logger.error(f"CloseAppTool error: {e}")
            return {
                "status": "error",
                "action": "close_app",
                "app": app_name,
                "message": str(e),
                "result": None,
                "verification": {"processes_closed": 0},
                "error": str(e)
            }


class FocusAppTool(Tool):
    """Focus an application window."""

    def __init__(self):
        super().__init__("focus_app", "Focus an application window", required_permission="A")

    def execute(self, **kwargs) -> dict:
        # Support both 'app_name' and 'app' parameter names for flexibility
        app_name = kwargs.get("app_name") or kwargs.get("app")
        if not app_name:
            return {
                "status": "error",
                "action": "focus_app",
                "app": None,
                "message": "Missing required parameter: app_name or app",
                "result": None,
                "verification": {"window_focused": False},
                "error": "Missing required parameter: app_name or app"
            }
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            success, message = engine.focus_app(app_name)
            return {
                "status": "success" if success else "error",
                "action": "focus_app",
                "app": app_name,
                "message": message,
                "result": {"focused": success},
                "verification": {"window_focused": success},
                "error": None if success else message
            }
        except Exception as e:
            logger.error(f"FocusAppTool error: {e}")
            return {
                "status": "error",
                "action": "focus_app",
                "app": app_name,
                "message": str(e),
                "result": None,
                "verification": {"window_focused": False},
                "error": str(e)
            }


class CreateFolderTool(Tool):
    """Create a folder."""

    def __init__(self):
        super().__init__("create_folder", "Create a folder", required_permission="A")

    def execute(self, **kwargs) -> dict:
        path = kwargs.get("path")
        if not path:
            return {
                "status": "error",
                "action": "create_folder",
                "path": None,
                "message": "Missing required parameter: path",
                "result": None,
                "verification": {"folder_exists": False},
                "error": "Missing required parameter: path"
            }
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            success, message = engine.create_folder(path)
            return {
                "status": "success" if success else "error",
                "action": "create_folder",
                "path": path,
                "message": message,
                "result": {"path": path} if success else None,
                "verification": {
                    "folder_exists": Path(path).exists() if success else False
                },
                "error": None if success else message
            }
        except Exception as e:
            logger.error(f"CreateFolderTool error: {e}")
            return {
                "status": "error",
                "action": "create_folder",
                "path": path,
                "message": str(e),
                "result": None,
                "verification": {"folder_exists": False},
                "error": str(e)
            }


class SearchFilesTool(Tool):
    """Search for files."""

    def __init__(self):
        super().__init__("search_files", "Search for files", required_permission="A")

    def execute(self, **kwargs) -> dict:
        query = kwargs.get("query", "")
        folder = kwargs.get("folder")
        if not query:
            return {
                "status": "error",
                "action": "search_files",
                "query": None,
                "folder": folder,
                "message": "Missing required parameter: query",
                "result": None,
                "verification": {"results_count": 0},
                "error": "Missing required parameter: query"
            }
        try:
            from alice.computer.file_operations import FileOperations
            from alice.core.config import Config
            config = Config.load()
            fo = FileOperations(config)
            results = fo.search_files(query, folder)
            return {
                "status": "success",
                "action": "search_files",
                "query": query,
                "folder": folder,
                "message": f"Found {len(results)} files",
                "result": {"files": results[:50]},  # Limit results
                "verification": {"results_count": len(results)},
                "error": None
            }
        except Exception as e:
            logger.error(f"SearchFilesTool error: {e}")
            return {
                "status": "error",
                "action": "search_files",
                "query": query,
                "folder": folder,
                "message": str(e),
                "result": None,
                "verification": {"results_count": 0},
                "error": str(e)
            }


class BrowserOpenTool(Tool):
    """Open a search or URL in ALICE's persistent, non-Incognito Chrome profile."""

    _managed_profile_dir: Optional[str] = None

    def __init__(self):
        super().__init__("browser_open", "Open Google Chrome or perform a web search", required_permission="A")

    @classmethod
    def _resolve_profile_dir(cls) -> Path:
        """Return a persistent profile directory reserved exclusively for ALICE."""
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data)
        else:
            root = Path.home() / "AppData" / "Local"
        return root / "ALICE" / "ChromeProfile"

    def _find_chrome_executable(self) -> Optional[str]:
        """Find the installed Chrome executable."""
        candidates = []
        for root_var, suffix in (
            ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
            ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
            ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
        ):
            root = os.environ.get(root_var)
            if root:
                candidates.append(Path(root) / suffix)

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return shutil.which("chrome.exe") or shutil.which("chrome")

    def _launch_chrome(self, url: Optional[str] = None, search: Optional[str] = None) -> dict:
        """Open Chrome with ALICE's separate, persistent regular browser profile."""
        from urllib.parse import urlencode, urlparse

        if search and not url:
            query = str(search).strip()
            if not query:
                return {"status": "error", "action": "browser_open", "error": "Search query is empty."}
            target_url = "https://www.google.com/search?" + urlencode({"q": query})
        elif url:
            target_url = str(url).strip()
            parsed = urlparse(target_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return {"status": "error", "action": "browser_open", "error": "URL must use http:// or https://."}
        else:
            return {"status": "error", "action": "browser_open", "error": "Provide a URL or search query."}

        chrome_path = self._find_chrome_executable()
        if not chrome_path:
            return {
                "status": "error", "action": "browser_open", "url": target_url,
                "error": "Google Chrome was not found. Install Chrome or add chrome.exe to PATH."
            }

        profile_dir = self._resolve_profile_dir()
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
            type(self)._managed_profile_dir = str(profile_dir.resolve())
            creation_flags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
            launch_kwargs = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            }
            if creation_flags:
                launch_kwargs["creationflags"] = creation_flags

            # This profile is stored under LocalAppData and reused between ALICE
            # sessions. It is a normal Chrome profile, not an Incognito session.
            # It is separate so that ALICE can close only its own Chrome windows.
            command = [
                chrome_path,
                f"--user-data-dir={profile_dir}",
                "--new-window",
                "--no-first-run",
                target_url
            ]
            process = subprocess.Popen(command, **launch_kwargs)
            return {
                "status": "success",
                "action": "browser_open",
                "browser": "Google Chrome",
                "search": search,
                "url": target_url,
                "profile": str(profile_dir),
                "message": "Opened Google Chrome in ALICE's persistent regular profile (not Incognito). Future searches reuse this profile.",
                "verification": {
                    "launch_requested": True,
                    "incognito": False,
                    "dedicated_profile": True,
                    "profile_dir": str(profile_dir),
                    "pid": getattr(process, "pid", None)
                },
                "error": None
            }
        except Exception as exc:
            logger.exception("Could not launch Google Chrome")
            return {"status": "error", "action": "browser_open", "url": target_url, "error": str(exc)}

    @classmethod
    def close_owned_browser(cls) -> dict:
        """Close only Chrome processes using ALICE's dedicated profile."""
        profile_dir = cls._managed_profile_dir or str(cls._resolve_profile_dir())
        target_profile = os.path.normcase(os.path.abspath(profile_dir))
        try:
            import psutil
            matches = []
            for process in psutil.process_iter(["name", "cmdline"]):
                try:
                    name = (process.info.get("name") or "").lower()
                    if "chrome" not in name:
                        continue
                    command_line = process.info.get("cmdline") or []
                    for argument in command_line:
                        if not isinstance(argument, str) or not argument.lower().startswith("--user-data-dir="):
                            continue
                        candidate = argument.split("=", 1)[1].strip('"')
                        if os.path.normcase(os.path.abspath(candidate)) == target_profile:
                            matches.append(process)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            if not matches:
                return {
                    "status": "success",
                    "action": "close_app",
                    "app": "chrome",
                    "message": "No ALICE-managed Chrome session is running; other Chrome windows were left untouched.",
                    "verification": {"closed_processes": 0}
                }

            for process in matches:
                try:
                    process.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            gone, alive = psutil.wait_procs(matches, timeout=4)
            for process in alive:
                try:
                    process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            cls._managed_profile_dir = None
            return {
                "status": "success",
                "action": "close_app",
                "app": "chrome",
                "message": f"Closed the ALICE-managed Chrome profile ({len(gone) + len(alive)} process(es)). Other Chrome profiles were left untouched.",
                "verification": {"closed_processes": len(gone) + len(alive)}
            }
        except ImportError:
            return {
                "status": "error",
                "action": "close_app",
                "app": "chrome",
                "error": "psutil is required to safely close only the ALICE-managed Chrome profile."
            }
        except Exception as exc:
            logger.exception("Could not close the ALICE-managed Chrome profile")
            return {"status": "error", "action": "close_app", "app": "chrome", "error": str(exc)}

    def execute(self, **kwargs) -> dict:
        """Launch Chrome visibly; the persistent browser profile outlives this call."""
        return self._launch_chrome(kwargs.get("url"), kwargs.get("search"))

    async def _browser_open_async(self, url: Optional[str] = None, search: Optional[str] = None, visible: bool = True) -> dict:
        """Async-compatible wrapper retained for existing callers and tests."""
        return await asyncio.to_thread(self._launch_chrome, url, search)


class BrowserExtractTool(Tool):
    """Extract text content from a web page using Playwright."""

    def __init__(self):
        super().__init__("browser_extract", "Extract text content from a web page", required_permission="A")

    def execute(self, **kwargs) -> dict:
        url = kwargs.get("url")
        selector = kwargs.get("selector")
        if not url:
            return {"status": "error", "error": "Missing required parameter: url"}
        import asyncio
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.ensure_future(self._browser_extract_async(url, selector))
                return {"status": "started", "url": url}
            else:
                result = loop.run_until_complete(self._browser_extract_async(url, selector))
                return result
        except Exception as e:
            logger.error(f"Browser extract error: {e}")
            return {"status": "error", "error": str(e)}

    async def _browser_extract_async(self, url: str, selector: Optional[str] = None, visible: bool = False) -> dict:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=not visible)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(url)
                await page.wait_for_load_state("networkidle")

                if selector:
                    element = await page.query_selector(selector)
                    content = await element.inner_text() if element else ""
                else:
                    content = await page.inner_text("body")

                title = await page.title()
                await browser.close()

                return {
                    "status": "success",
                    "action": "browser_extract",
                    "url": url,
                    "title": title,
                    "content": content[:5000],
                    "selector": selector,
                    "verification": {"content_length": len(content)},
                    "error": None
                }
        except ImportError:
            return {"status": "error", "error": "playwright not installed"}
        except Exception as e:
            logger.error(f"Browser extract async error: {e}")
            return {"status": "error", "error": str(e)}


class BrowserDownloadTool(Tool):
    """Download a file from the web using Playwright."""

    def __init__(self):
        super().__init__("browser_download", "Download a file from the web", required_permission="B")

    def execute(self, **kwargs) -> dict:
        url = kwargs.get("url")
        destination = kwargs.get("destination")
        if not url:
            return {"status": "error", "error": "Missing required parameter: url"}
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.ensure_future(self._browser_download_async(url, destination))
                return {"status": "started", "url": url}
            else:
                result = loop.run_until_complete(self._browser_download_async(url, destination))
                return result
        except Exception as e:
            logger.error(f"Browser download error: {e}")
            return {"status": "error", "error": str(e)}

    async def _browser_download_async(self, url: str, destination: Optional[str] = None) -> dict:
        try:
            from playwright.async_api import async_playwright
            from pathlib import Path

            if destination is None:
                destination = str(Path.home() / "Downloads" / url.split("/")[-1].split("?")[0])

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                async with page.expect_download() as download_info:
                    await page.goto(url)
                download = await download_info.value
                await download.save_as(destination)

                await browser.close()

                return {
                    "status": "success",
                    "action": "browser_download",
                    "url": url,
                    "path": destination,
                    "size": Path(destination).stat().st_size if Path(destination).exists() else 0,
                    "verification": {"file_exists": Path(destination).exists()},
                    "error": None
                }
        except ImportError:
            return {"status": "error", "error": "playwright not installed"}
        except Exception as e:
            logger.error(f"Browser download async error: {e}")
            return {"status": "error", "error": str(e)}


class BrowserScreenshotTool(Tool):
    """Take a screenshot of a web page using Playwright."""

    def __init__(self):
        super().__init__("browser_screenshot", "Take a screenshot of a web page", required_permission="A")

    def execute(self, **kwargs) -> dict:
        url = kwargs.get("url")
        full_page = kwargs.get("full_page", True)
        destination = kwargs.get("destination")
        visible = kwargs.get("visible", False)
        if not url:
            return {"status": "error", "error": "Missing required parameter: url"}
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.ensure_future(self._browser_screenshot_async(url, full_page, destination, visible))
                return {"status": "started", "url": url}
            else:
                result = loop.run_until_complete(self._browser_screenshot_async(url, full_page, destination, visible))
                return result
        except Exception as e:
            logger.error(f"Browser screenshot error: {e}")
            return {"status": "error", "error": str(e)}

    async def _browser_screenshot_async(self, url: str, full_page: bool = True, destination: Optional[str] = None, visible: bool = False) -> dict:
        try:
            from playwright.async_api import async_playwright
            from pathlib import Path

            if destination is None:
                destination = str(Path.home() / "Downloads" / f"screenshot_{url.replace('https://', '').replace('/', '_')[:50]}.png")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=not visible)
                context = await browser.new_context()
                page = await context.new_page()

                await page.goto(url)
                await page.wait_for_load_state("networkidle")

                await page.screenshot(path=destination, full_page=full_page)

                await browser.close()

                return {
                    "status": "success",
                    "action": "browser_screenshot",
                    "url": url,
                    "path": destination,
                    "full_page": full_page,
                    "size": Path(destination).stat().st_size if Path(destination).exists() else 0,
                    "verification": {"file_exists": Path(destination).exists()},
                    "error": None
                }
        except ImportError:
            return {"status": "error", "error": "playwright not installed"}
        except Exception as e:
            logger.error(f"Browser screenshot async error: {e}")
            return {"status": "error", "error": str(e)}


class CloseAllAppsTool(Tool):
    """Close all applications opened by ALICE."""

    def __init__(self):
        super().__init__("close_all_apps", "Close all applications opened by ALICE", required_permission="B")

    def execute(self, **kwargs) -> dict:
        try:
            from alice.core.application_owner import ApplicationOwner
            owner = ApplicationOwner.get_instance()
            results = owner.close_all_apps()
            return {
                "status": "success",
                "action": "close_all_apps",
                "message": f"Closed {results['total']} applications",
                "result": results,
                "verification": {"total_closed": results.get("total", 0)},
                "error": None
            }
        except Exception as e:
            logger.error(f"CloseAllAppsTool error: {e}")
            return {"status": "error", "error": str(e)}


class GetOpenAppsTool(Tool):
    """Get list of applications opened by ALICE."""

    def __init__(self):
        super().__init__("get_open_apps", "Get list of applications opened by ALICE", required_permission="A")

    def execute(self, **kwargs) -> dict:
        try:
            from alice.core.application_owner import ApplicationOwner
            owner = ApplicationOwner.get_instance()
            apps = owner.get_owned_apps()
            return {
                "status": "success",
                "action": "get_open_apps",
                "message": f"Found {len(apps)} opened applications",
                "result": {"apps": apps},
                "verification": {"apps_count": len(apps)},
                "error": None
            }
        except Exception as e:
            logger.error(f"GetOpenAppsTool error: {e}")
            return {"status": "error", "error": str(e)}


class GetAppStatusTool(Tool):
    """Get status of a specific application opened by ALICE."""

    def __init__(self):
        super().__init__("get_app_status", "Get status of a specific application", required_permission="A")

    def execute(self, **kwargs) -> dict:
        app_name = kwargs.get("app_name") or kwargs.get("app")
        if not app_name:
            return {"status": "error", "error": "Missing required parameter: app_name"}
        try:
            from alice.core.application_owner import ApplicationOwner
            owner = ApplicationOwner.get_instance()
            status = owner.get_status()
            app_info = owner.get_apps_by_name(app_name)
            return {
                "status": "success",
                "action": "get_app_status",
                "app": app_name,
                "message": f"Status for {app_name}",
                "result": {
                    "app": app_name,
                    "instances": app_info,
                    "total_owned": status["total_owned"]
                },
                "verification": {"has_instances": len(app_info) > 0},
                "error": None
            }
        except Exception as e:
            logger.error(f"GetAppStatusTool error: {e}")
            return {"status": "error", "error": str(e)}


class TypeTextTool(Tool):
    """Paste text into a deliberately focused target window."""

    def __init__(self):
        super().__init__("type_text", "Type text into the active window", required_permission="B")

    def execute(self, **kwargs) -> dict:
        text = kwargs.get("text", "")
        delay = max(0.0, float(kwargs.get("delay", 0) or 0))
        target_window = kwargs.get("target_window")
        if not isinstance(text, str) or not text:
            return {"status": "error", "action": "type_text", "error": "Missing required parameter: text"}

        try:
            import time
            from alice.computer.engine import ComputerEngine
            from alice.tools.clipboard_utils import set_text_to_clipboard

            engine = ComputerEngine()
            if target_window:
                focused, focus_message = engine.focus_app(str(target_window))
            else:
                focused = engine.auto_focus_most_relevant()
                focus_message = "Focused the most recently relevant application" if focused else "No target window could be focused"

            # Never paste into an arbitrary foreground window after a failed focus.
            if not focused:
                return {
                    "status": "error",
                    "action": "type_text",
                    "target_window": target_window,
                    "message": focus_message,
                    "error": f"Could not focus the requested target window: {target_window or 'active application'}"
                }

            time.sleep(max(0.3, delay))
            result = set_text_to_clipboard(text, target_window=target_window)
            if result.get("status") != "success":
                return {
                    "status": "error",
                    "action": "type_text",
                    "target_window": target_window,
                    "message": "Text was not pasted.",
                    "error": result.get("error", "Clipboard paste failed")
                }

            return {
                "status": "success",
                "action": "type_text",
                "target_window": target_window,
                "message": f"Sent the paste shortcut to the focused window{': ' + str(target_window) if target_window else ''}.",
                "result": {"characters": len(text), "method": "clipboard_paste"},
                "verification": {"focus_confirmed": True, "paste_shortcut_sent": True},
                "error": None
            }
        except ImportError as exc:
            return {"status": "error", "action": "type_text", "error": f"Missing automation dependency: {exc}"}
        except Exception as exc:
            logger.exception("TypeTextTool error")
            return {"status": "error", "action": "type_text", "error": str(exc)}


class KeyboardShortcutTool(Tool):
    """Execute a keyboard shortcut."""

    def __init__(self):
        super().__init__("keyboard_shortcut", "Execute a keyboard shortcut", required_permission="B")

    def execute(self, **kwargs) -> dict:
        keys = kwargs.get("keys", "")
        if not keys:
            return {"status": "error", "error": "Missing required parameter: keys"}
        try:
            import pyautogui
            pyautogui.hotkey(*keys.split('+'))
            return {
                "status": "success",
                "action": "keyboard_shortcut",
                "keys": keys,
                "message": f"Executed keyboard shortcut: {keys}",
                "result": {"executed": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"KeyboardShortcutTool error: {e}")
            return {"status": "error", "error": str(e)}


class MouseMoveTool(Tool):
    """Move mouse to coordinates."""

    def __init__(self):
        super().__init__("mouse_move", "Move mouse to coordinates", required_permission="B")

    def execute(self, **kwargs) -> dict:
        x = kwargs.get("x", 0)
        y = kwargs.get("y", 0)
        duration = kwargs.get("duration", 0)
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return {
                "status": "success",
                "action": "mouse_move",
                "coordinates": {"x": x, "y": y},
                "message": f"Moved mouse to ({x}, {y})",
                "result": {"moved": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"MouseMoveTool error: {e}")
            return {"status": "error", "error": str(e)}


class MouseClickTool(Tool):
    """Click mouse."""

    def __init__(self):
        super().__init__("mouse_click", "Click mouse", required_permission="B")

    def execute(self, **kwargs) -> dict:
        x = kwargs.get("x")
        y = kwargs.get("y")
        button = kwargs.get("button", "left")
        clicks = kwargs.get("clicks", 1)
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            return {
                "status": "success",
                "action": "mouse_click",
                "button": button,
                "clicks": clicks,
                "message": f"Clicked {button} button {clicks} time(s)",
                "result": {"clicked": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"MouseClickTool error: {e}")
            return {"status": "error", "error": str(e)}


class MouseScrollTool(Tool):
    """Scroll mouse wheel."""

    def __init__(self):
        super().__init__("mouse_scroll", "Scroll mouse wheel", required_permission="B")

    def execute(self, **kwargs) -> dict:
        clicks = kwargs.get("clicks", 3)
        x = kwargs.get("x")
        y = kwargs.get("y")
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.scroll(clicks, x=x, y=y)
            else:
                pyautogui.scroll(clicks)
            return {
                "status": "success",
                "action": "mouse_scroll",
                "clicks": clicks,
                "message": f"Scrolled mouse wheel by {clicks}",
                "result": {"scrolled": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"MouseScrollTool error: {e}")
            return {"status": "error", "error": str(e)}


class SelectTextTool(Tool):
    """Select text."""

    def __init__(self):
        super().__init__("select_text", "Select text", required_permission="B")

    def execute(self, **kwargs) -> dict:
        method = kwargs.get("method", "all")
        try:
            import pyautogui
            if method == "all":
                pyautogui.hotkey('ctrl', 'a')
            elif method == "word":
                pyautogui.hotkey('ctrl', 'shift', 'right')
            elif method == "line":
                pyautogui.hotkey('ctrl', 'shift', 'down')
            elif method == "paragraph":
                pyautogui.hotkey('ctrl', 'shift', 'down')
            return {
                "status": "success",
                "action": "select_text",
                "method": method,
                "message": f"Selected text using {method} method",
                "result": {"selected": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"SelectTextTool error: {e}")
            return {"status": "error", "error": str(e)}


class CopyPasteTool(Tool):
    """Copy, cut, or paste text."""

    def __init__(self):
        super().__init__("copy_paste", "Copy, cut, or paste text", required_permission="B")

    def execute(self, **kwargs) -> dict:
        action = kwargs.get("action", "copy")
        if action not in ("copy", "cut", "paste"):
            return {"status": "error", "error": f"Invalid action: {action}. Must be copy, cut, or paste"}
        try:
            import pyautogui
            if action == "copy":
                pyautogui.hotkey('ctrl', 'c')
            elif action == "cut":
                pyautogui.hotkey('ctrl', 'x')
            elif action == "paste":
                pyautogui.hotkey('ctrl', 'v')
            return {
                "status": "success",
                "action": "copy_paste",
                "operation": action,
                "message": f"Performed {action} operation",
                "result": {"executed": True},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"CopyPasteTool error: {e}")
            return {"status": "error", "error": str(e)}


class GetClipboardTool(Tool):
    """Get clipboard content."""

    def __init__(self):
        super().__init__("get_clipboard", "Get clipboard content", required_permission="A")

    def execute(self, **kwargs) -> dict:
        try:
            import pyperclip
            content = pyperclip.paste()
            return {
                "status": "success",
                "action": "get_clipboard",
                "message": "Retrieved clipboard content",
                "result": {"content": content, "length": len(content)},
                "verification": {"has_content": bool(content)},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyperclip not installed"}
        except Exception as e:
            logger.error(f"GetClipboardTool error: {e}")
            return {"status": "error", "error": str(e)}


class SetClipboardTool(Tool):
    """Set clipboard content."""

    def __init__(self):
        super().__init__("set_clipboard", "Set clipboard content", required_permission="B")

    def execute(self, **kwargs) -> dict:
        content = kwargs.get("content", "")
        if not content:
            return {"status": "error", "error": "Missing required parameter: content"}
        try:
            import pyperclip
            pyperclip.copy(content)
            return {
                "status": "success",
                "action": "set_clipboard",
                "message": "Set clipboard content",
                "result": {"length": len(content)},
                "verification": {"success": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyperclip not installed"}
        except Exception as e:
            logger.error(f"SetClipboardTool error: {e}")
            return {"status": "error", "error": str(e)}


class ToolDispatcher:
    """Central dispatcher for tool execution with async support."""

    def __init__(self, tool_registry: ToolRegistry, config: Any):
        self.tool_registry = tool_registry
        self.config = config
        automation = getattr(config, 'automation', None)
        self.max_tool_calls = getattr(automation, 'max_tool_calls', 5) or 5
        self.call_count = 0

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with arguments.

        Handles async tools by running them in an event loop if needed.
        """
        from alice.core.config import Config
        config = Config.load()
        self.call_count += 1
        if self.call_count > self.max_tool_calls:
            return {"status": "error", "error": f"Exceeded maximum tool calls ({self.max_tool_calls})"}

        tool = self.tool_registry.get(tool_name)
        if not tool:
            return {"status": "error", "error": f"Tool '{tool_name}' not found"}

        try:
            result = tool.execute(**arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return {"status": "error", "error": str(e)}

    async def execute_async(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool asynchronously without blocking the chat event loop."""
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return {"status": "error", "error": f"Tool '{tool_name}' not found"}

        self.call_count += 1
        if self.call_count > self.max_tool_calls:
            return {"status": "error", "error": f"Exceeded maximum tool calls ({self.max_tool_calls})"}

        try:
            async_method = getattr(tool, "_execute_async", None)
            if callable(async_method):
                result = await async_method(**arguments)
            else:
                result = await asyncio.to_thread(tool.execute, **arguments)
            return result if isinstance(result, dict) else {"status": "success", "result": result}
        except Exception as exc:
            logger.exception("Async tool execution error for %s", tool_name)
            return {"status": "error", "error": str(exc)}



def create_default_tools() -> ToolRegistry:
    """Create and register all default tools."""
    registry = ToolRegistry()

    # App control tools
    registry.register(OpenAppTool())
    registry.register(CloseAppTool())
    registry.register(FocusAppTool())

    # File and folder tools
    registry.register(CreateFolderTool())
    registry.register(SearchFilesTool())

    # Browser tools
    registry.register(BrowserOpenTool())
    registry.register(BrowserExtractTool())
    registry.register(BrowserDownloadTool())
    registry.register(BrowserScreenshotTool())

    # ALICE lifecycle tools
    registry.register(CloseAllAppsTool())
    registry.register(GetOpenAppsTool())
    registry.register(GetAppStatusTool())

    # Input simulation tools
    registry.register(TypeTextTool())
    registry.register(KeyboardShortcutTool())
    registry.register(MouseMoveTool())
    registry.register(MouseClickTool())
    registry.register(MouseScrollTool())
    registry.register(SelectTextTool())
    registry.register(CopyPasteTool())
    registry.register(GetClipboardTool())
    registry.register(SetClipboardTool())

    return registry