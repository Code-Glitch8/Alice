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

    def execute(self, app_name: str) -> dict:
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            success, message, details = engine.open_app(app_name)
            return {
                "status": "success" if success else "error",
                "action": "open_app",
                "app": app_name,
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

    def execute(self, app_name: str) -> dict:
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

    def execute(self, app_name: str) -> dict:
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

    def execute(self, path: str) -> dict:
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

    def execute(self, query: str, folder: Optional[str] = None) -> dict:
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
                "message": str(e),
                "result": None,
                "verification": {"results_count": 0},
                "error": str(e)
            }


class BrowserOpenTool(Tool):
    """Open browser with URL or search using Playwright."""

    def __init__(self):
        super().__init__("browser_open", "Open browser or perform search", required_permission="A")

    def execute(self, url: Optional[str] = None, search: Optional[str] = None) -> dict:
        """Execute browser open/search.

        If search is provided and no URL, performs a web search.
        If URL is provided, navigates to it.
        Returns status dict with execution result.
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.ensure_future(self._browser_open_async(url, search))
                return {"status": "started", "url": url, "search": search}
            else:
                result = loop.run_until_complete(self._browser_open_async(url, search))
                return result
        except Exception as e:
            logger.error(f"Browser open error: {e}")
            return {"status": "error", "error": str(e)}

    async def _browser_open_async(self, url: Optional[str] = None, search: Optional[str] = None) -> dict:
        """Async browser open using Playwright."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                if search and not url:
                    query = search if isinstance(search, str) else str(search)
                    await page.goto(f"https://www.google.com/search?q={query}")
                    await page.wait_for_load_state("networkidle")
                    title = await page.title()
                    current_url = page.url
                    await browser.close()
                    return {
                        "status": "search_completed",
                        "action": "browser_open",
                        "search": query,
                        "title": title,
                        "url": current_url,
                        "verification": {"page_loaded": True},
                        "error": None
                    }
                elif url:
                    await page.goto(url)
                    await page.wait_for_load_state("networkidle")
                    title = await page.title()
                    current_url = page.url
                    await browser.close()
                    return {
                        "status": "navigated",
                        "action": "browser_open",
                        "url": url,
                        "title": title,
                        "verification": {"page_loaded": True},
                        "error": None
                    }
                else:
                    await browser.close()
                    return {"status": "idle", "error": "No URL or search provided"}
        except ImportError:
            return {"status": "error", "error": "playwright not installed"}
        except Exception as e:
            logger.error(f"Browser async error: {e}")
            return {"status": "error", "error": str(e)}


class BrowserExtractTool(Tool):
    """Extract text content from a web page using Playwright."""

    def __init__(self):
        super().__init__("browser_extract", "Extract text content from a web page", required_permission="A")

    def execute(self, url: str, selector: Optional[str] = None) -> dict:
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

    async def _browser_extract_async(self, url: str, selector: Optional[str] = None) -> dict:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
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

    def execute(self, url: str, destination: Optional[str] = None) -> dict:
        import asyncio
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

    def execute(self, url: str, full_page: bool = True, destination: Optional[str] = None) -> dict:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.ensure_future(self._browser_screenshot_async(url, full_page, destination))
                return {"status": "started", "url": url}
            else:
                result = loop.run_until_complete(self._browser_screenshot_async(url, full_page, destination))
                return result
        except Exception as e:
            logger.error(f"Browser screenshot error: {e}")
            return {"status": "error", "error": str(e)}

    async def _browser_screenshot_async(self, url: str, full_page: bool = True, destination: Optional[str] = None) -> dict:
        try:
            from playwright.async_api import async_playwright
            from pathlib import Path

            if destination is None:
                destination = str(Path.home() / "Downloads" / f"screenshot_{url.replace('https://', '').replace('/', '_')[:50]}.png")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
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


class TypeTextTool(Tool):
    """Type text into the active window."""

    def __init__(self):
        super().__init__("type_text", "Type text into the active window", required_permission="A")

    def execute(self, text: str, delay: float = 0.05) -> dict:
        try:
            import pyautogui
            pyautogui.write(text, interval=delay)
            return {
                "status": "success",
                "action": "type_text",
                "text": text,
                "message": f"Typed {len(text)} characters",
                "result": {"chars_typed": len(text)},
                "verification": {"attempted": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"TypeTextTool error: {e}")
            return {"status": "error", "error": str(e)}


class KeyboardShortcutTool(Tool):
    """Execute a keyboard shortcut."""

    def __init__(self):
        super().__init__("keyboard_shortcut", "Execute a keyboard shortcut", required_permission="A")

    def execute(self, keys: str) -> dict:
        try:
            import pyautogui
            # Parse keys like "ctrl+c", "alt+tab", "win+d"
            key_list = [k.strip() for k in keys.split('+')]
            pyautogui.hotkey(*key_list)
            return {
                "status": "success",
                "action": "keyboard_shortcut",
                "keys": keys,
                "message": f"Executed shortcut: {keys}",
                "result": {"keys": key_list},
                "verification": {"attempted": True},
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
        super().__init__("mouse_move", "Move mouse to coordinates", required_permission="A")

    def execute(self, x: int, y: int, duration: float = 0.5) -> dict:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            return {
                "status": "success",
                "action": "mouse_move",
                "x": x,
                "y": y,
                "message": f"Moved mouse to ({x}, {y})",
                "result": {"position": [x, y]},
                "verification": {"position": pyautogui.position()},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"MouseMoveTool error: {e}")
            return {"status": "error", "error": str(e)}


class MouseClickTool(Tool):
    """Click mouse at current or specified position."""

    def __init__(self):
        super().__init__("mouse_click", "Click mouse", required_permission="A")

    def execute(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> dict:
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            return {
                "status": "success",
                "action": "mouse_click",
                "x": x,
                "y": y,
                "button": button,
                "clicks": clicks,
                "message": f"Clicked {button} button {clicks} time(s)",
                "result": {"position": [x, y] if x is not None else list(pyautogui.position())},
                "verification": {"attempted": True},
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
        super().__init__("mouse_scroll", "Scroll mouse wheel", required_permission="A")

    def execute(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> dict:
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
                "message": f"Scrolled {clicks} clicks",
                "result": {"clicks": clicks},
                "verification": {"attempted": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"MouseScrollTool error: {e}")
            return {"status": "error", "error": str(e)}


class SelectTextTool(Tool):
    """Select text using keyboard shortcuts."""

    def __init__(self):
        super().__init__("select_text", "Select text", required_permission="A")

    def execute(self, method: str = "all") -> dict:
        """Select text. method: 'all', 'word', 'line', 'paragraph'"""
        try:
            import pyautogui
            if method == "all":
                pyautogui.hotkey('ctrl', 'a')
            elif method == "word":
                pyautogui.hotkey('ctrl', 'shift', 'right')
            elif method == "line":
                pyautogui.hotkey('shift', 'end')
            elif method == "paragraph":
                pyautogui.hotkey('ctrl', 'shift', 'down')
            else:
                return {"status": "error", "error": f"Unknown method: {method}"}

            return {
                "status": "success",
                "action": "select_text",
                "method": method,
                "message": f"Selected text ({method})",
                "result": {"method": method},
                "verification": {"attempted": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"SelectTextTool error: {e}")
            return {"status": "error", "error": str(e)}


class CopyPasteTool(Tool):
    """Copy, cut, or paste clipboard content."""

    def __init__(self):
        super().__init__("copy_paste", "Copy, cut, or paste", required_permission="A")

    def execute(self, action: str) -> dict:
        """action: 'copy', 'cut', 'paste'"""
        try:
            import pyautogui
            if action == "copy":
                pyautogui.hotkey('ctrl', 'c')
            elif action == "cut":
                pyautogui.hotkey('ctrl', 'x')
            elif action == "paste":
                pyautogui.hotkey('ctrl', 'v')
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

            return {
                "status": "success",
                "action": "copy_paste",
                "operation": action,
                "message": f"{action.capitalize()} executed",
                "result": {"operation": action},
                "verification": {"attempted": True},
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

    def execute(self) -> dict:
        try:
            import pyperclip
            content = pyperclip.paste()
            return {
                "status": "success",
                "action": "get_clipboard",
                "content": content[:1000],  # Limit size
                "message": f"Clipboard content retrieved ({len(content)} chars)",
                "result": {"content": content},
                "verification": {"retrieved": True},
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
        super().__init__("set_clipboard", "Set clipboard content", required_permission="A")

    def execute(self, content: str) -> dict:
        try:
            import pyperclip
            pyperclip.copy(content)
            return {
                "status": "success",
                "action": "set_clipboard",
                "content": content[:100],
                "message": f"Clipboard set ({len(content)} chars)",
                "result": {"length": len(content)},
                "verification": {"set": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyperclip not installed"}
        except Exception as e:
            logger.error(f"SetClipboardTool error: {e}")
            return {"status": "error", "error": str(e)}


class EmergencyStopTool(Tool):
    """Emergency stop all automation."""

    def __init__(self):
        super().__init__("emergency_stop", "Emergency stop all automation", required_permission="A")

    def execute(self) -> dict:
        try:
            import pyautogui
            # Move mouse to corner to trigger failsafe
            pyautogui.FAILSAFE = True
            pyautogui.moveTo(0, 0)
            return {
                "status": "success",
                "action": "emergency_stop",
                "message": "Emergency stop triggered - mouse moved to corner",
                "result": {"failsafe_triggered": True},
                "verification": {"stopped": True},
                "error": None
            }
        except ImportError:
            return {"status": "error", "error": "pyautogui not installed"}
        except Exception as e:
            logger.error(f"EmergencyStopTool error: {e}")
            return {"status": "error", "error": str(e)}


class SystemInfoTool(Tool):
    """Get system information."""

    def __init__(self):
        super().__init__("system_info", "Get system information", required_permission="A")

    def execute(self) -> dict:
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            info = engine.get_system_info()
            return {
                "status": "success",
                "action": "system_info",
                "message": "System info retrieved",
                "result": info,
                "verification": {"retrieved": True},
                "error": None
            }
        except Exception as e:
            logger.error(f"SystemInfoTool error: {e}")
            return {"status": "error", "error": str(e)}


class ListRunningAppsTool(Tool):
    """List running applications."""

    def __init__(self):
        super().__init__("list_running_apps", "List running applications", required_permission="A")

    def execute(self) -> dict:
        try:
            from alice.computer.engine import ComputerEngine
            from alice.core.config import Config
            config = Config.load()
            engine = ComputerEngine(config)
            apps = engine.get_running_apps()
            return {
                "status": "success",
                "action": "list_running_apps",
                "message": f"Found {len(apps)} running apps",
                "result": {"apps": apps[:50]},
                "verification": {"count": len(apps)},
                "error": None
            }
        except Exception as e:
            logger.error(f"ListRunningAppsTool error: {e}")
            return {"status": "error", "error": str(e)}


class SaveFileTool(Tool):
    """Save content to a file."""

    def __init__(self):
        super().__init__("save_file", "Save content to a file", required_permission="A")

    def execute(self, path: str, content: Optional[str] = None) -> dict:
        try:
            from alice.computer.file_operations import FileOperations
            from alice.core.config import Config
            config = Config.load()
            fo = FileOperations(config)
            success, message, details = fo.save_file(path, content)
            return {
                "status": "success" if success else "error",
                "action": "save_file",
                "path": path,
                "message": message,
                "result": details if success else None,
                "verification": {"file_exists": Path(path).exists() if success else False},
                "error": None if success else message
            }
        except Exception as e:
            logger.error(f"SaveFileTool error: {e}")
            return {
                "status": "error",
                "action": "save_file",
                "path": path,
                "message": str(e),
                "result": None,
                "verification": {"file_exists": False},
                "error": str(e)
            }


# Tool factory
def create_default_tools() -> ToolRegistry:
    """Create and register default tools."""
    registry = ToolRegistry()

    registry.register(OpenAppTool())
    registry.register(CloseAppTool())
    registry.register(FocusAppTool())
    registry.register(CreateFolderTool())
    registry.register(SearchFilesTool())
    registry.register(BrowserOpenTool())
    registry.register(BrowserExtractTool())
    registry.register(BrowserDownloadTool())
    registry.register(BrowserScreenshotTool())
    registry.register(TypeTextTool())
    registry.register(KeyboardShortcutTool())
    registry.register(MouseMoveTool())
    registry.register(MouseClickTool())
    registry.register(MouseScrollTool())
    registry.register(SelectTextTool())
    registry.register(CopyPasteTool())
    registry.register(GetClipboardTool())
    registry.register(SetClipboardTool())
    registry.register(EmergencyStopTool())
    registry.register(SystemInfoTool())
    registry.register(ListRunningAppsTool())
    registry.register(SaveFileTool())

    return registry


if __name__ == "__main__":
    # Test
    registry = create_default_tools()
    print(f"Registered tools: {[t.name for t in registry.list_tools()]}")