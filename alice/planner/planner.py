#!/usr/bin/env python3
"""
Natural Language Task Planner for ALICE.
Breaks down user requests into ordered steps, identifies dependencies,
and executes them with verification.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TaskStep:
    """Represents a single step in a task execution plan."""

    def __init__(self, step_id: int, description: str,
                 tool_name: str, parameters: Dict[str, Any],
                 requires_confirmation: bool = False):
        self.step_id = step_id
        self.description = description
        self.tool_name = tool_name
        self.parameters = parameters
        self.requires_confirmation = requires_confirmation
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.verified: bool = False

    def execute(self, tool_executor) -> bool:
        """Execute this step using the tool executor."""
        # Use get() which is the actual method on ToolRegistry
        tool = tool_executor.get(self.tool_name)
        if tool is None:
            self.error = f"Tool '{self.tool_name}' not found"
            logger.error(self.error)
            return False

        try:
            self.result = tool.execute(**self.parameters)
            return True
        except Exception as e:
            self.error = str(e)
            logger.error(f"Step {self.step_id} error: {e}")
            return False

    def verify(self) -> bool:
        """Verify the step result."""
        if self.error:
            self.verified = False
            return False

        # Simple verification: check result has success status
        if isinstance(self.result, dict):
            self.verified = self.result.get("status") == "success"
        else:
            self.verified = bool(self.result)

        return self.verified


class TaskPlanner:
    """Natural language task planner for ALICE."""

    def __init__(self, tool_registry: Any):
        self.tool_registry = tool_registry
        self.steps: List[TaskStep] = []

    def plan(self, user_intent: str) -> List[TaskStep]:
        """Break down user intent into ordered, executable steps."""
        import re
        intent_lower = user_intent.lower().strip()

        # Deterministic system inventory action must be recognized before generic
        # open/search handling; otherwise small local models can loop on it.
        if any(phrase in intent_lower for phrase in (
            "list all the apps", "list all apps", "show installed apps",
            "list installed applications", "what apps are installed",
            "all installed programs", "applications on my pc", "apps on my pc",
        )):
            steps = [TaskStep(1, "List installed applications", "list_installed_apps", {})]
        elif "search the web for " in intent_lower or "search web for " in intent_lower:
            steps = self._plan_browser_search(user_intent)
        elif (
            any(phrase in intent_lower for phrase in ("where is ", "locate ", "find ", "look for "))
            or ("search for " in intent_lower and any(word in intent_lower for word in ("folder", "directory", "file", "path")))
        ):
            steps = self._plan_search_files(user_intent)
        elif "search for " in intent_lower:
            steps = self._plan_browser_search(user_intent)
        elif "download " in intent_lower:
            steps = self._plan_browser_download(user_intent)
        elif any(kw in intent_lower for kw in ("screenshot", "capture ")):
            steps = self._plan_browser_screenshot(user_intent)
        elif any(kw in intent_lower for kw in ("extract from ", "summarize ", "read page", "get content")):
            steps = self._plan_browser_extract(user_intent)
        elif any(kw in intent_lower for kw in ("close ", "quit ", "exit ")):
            steps = self._plan_close_app(user_intent)
        elif any(kw in intent_lower for kw in ("open", "launch", "start")) and "chrome" in intent_lower:
            steps = [TaskStep(1, "Open Google Chrome", "browser_open", {"url": "https://www.google.com/", "visible": True})]
        elif any(kw in intent_lower for kw in ("open", "launch", "start")):
            steps = self._plan_open_app(user_intent)
        elif any(kw in intent_lower for kw in ("browser", "search chrome", "search web")):
            steps = self._plan_browser_search(user_intent)
        elif any(kw in intent_lower for kw in ("create", "make")):
            steps = self._plan_create(user_intent)
        elif any(kw in intent_lower for kw in ("extract", "unzip")):
            steps = self._plan_extract_zip(user_intent)
        elif any(kw in intent_lower for kw in ("help", "explain")):
            steps = self._plan_general_help(user_intent)
        else:
            steps = [TaskStep(1, user_intent, "general", {"intent": user_intent}, requires_confirmation=True)]

        self.steps = steps
        return steps

    def _extract_app_name(self, intent: str) -> str:
        """Extract application name from user intent."""
        intent = intent.lower().strip()
        # Remove common prefixes
        for prefix in ["open ", "launch ", "start ", "close ", "quit ", "exit "]:
            if intent.startswith(prefix):
                intent = intent[len(prefix):]
                break

        # If intent contains commas or clauses like "open notepad, type ...", take the first part
        for sep in [",", " and ", " then "]:
            if sep in intent:
                intent = intent.split(sep)[0]
                break

        return intent.strip()

    def _plan_close_app(self, intent: str) -> List[TaskStep]:
        """Plan closing an application through its registered ownership-aware tool."""
        app_name = self._extract_app_name(intent)
        return [
            TaskStep(1, f"Close {app_name}", "close_app", {"app_name": app_name},
                     requires_confirmation=True)
        ]

    def _plan_open_app(self, intent: str) -> List[TaskStep]:
        """Plan opening an application and optional text entry/save actions."""
        import re

        app_name = self._extract_app_name(intent)
        steps = [TaskStep(1, f"Open {app_name}", "open_app", {"app_name": app_name})]

        # Distinguish literal text supplied by the user from a request to
        # compose content. Never paste the instruction itself as the document.
        note_match = re.search(
            r'\\b(?:write|create|make)\\s+(?:a\\s+)?short\\s+(?:note|paragraph)\\s+(?:on|about)\\s+(.+?)(?:[.!?]?$)',
            intent, flags=re.IGNORECASE
        )
        write_match = re.search(
            r'\\b(?:type|write|enter)\\s+(.+?)(?=\\s*(?:,?\\s*(?:and\\s+)?save\\s+as\\b|$))',
            intent, flags=re.IGNORECASE | re.DOTALL
        )
        if note_match:
            topic = note_match.group(1).strip().rstrip(" .!?")
            steps.append(TaskStep(2, f"Focus {app_name}", "focus_app", {"app_name": app_name}))
            if "notepad" in app_name.lower():
                steps.append(TaskStep(3, "Open a new blank Notepad document", "keyboard_shortcut", {"keys": "ctrl+n"}))
            steps.append(TaskStep(
                len(steps) + 1, f"Write a short note about {topic}", "type_text",
                {"generate_topic": topic, "target_window": app_name}
            ))
            text = None
        elif write_match:
            supplied = write_match.group(1).strip()
            if (len(supplied) >= 2 and supplied[0] == supplied[-1] and supplied[0] in "\\\"'"):
                text = supplied[1:-1]
            elif supplied.lower().startswith("exactly "):
                text = supplied[8:].strip()
            else:
                text = None
            if text:
                steps.append(TaskStep(2, f"Focus {app_name}", "focus_app", {"app_name": app_name}))
                if "notepad" in app_name.lower():
                    steps.append(TaskStep(3, "Open a new blank Notepad document", "keyboard_shortcut", {"keys": "ctrl+n"}))
                steps.append(TaskStep(
                    len(steps) + 1, f"Write supplied text in {app_name}", "type_text",
                    {"text": text, "target_window": app_name}
                ))

        save_match = re.search(r"\bsave\s+as\s+([^\s,]+)", intent, flags=re.IGNORECASE)
        if save_match:
            filename = save_match.group(1)
            from pathlib import Path

            # Use Windows known folder resolution for reliability
            def get_known_folder_path(folder_name: str) -> Optional[Path]:
                """Get Windows known folder path using Shell32 API."""
                if os.name != "nt":
                    return None
                try:
                    import ctypes
                    from ctypes import wintypes

                    # Folder GUIDs
                    folder_guids = {
                        "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                        "Documents": "{FDD39AD8-70D2-4664-B824-9D18820A6B39}",
                        "Downloads": "{338E6FE1-3C68-4A47-B188-7540A5DD143}",
                    }

                    from uuid import UUID
                    guid_str = folder_guids.get(folder_name)
                    if not guid_str:
                        return None

                    guid = UUID(guid_str)
                    guid_struct = wintypes.GUID(guid.int, guid.bytes_le[3], guid.bytes_le[2],
                                                (guid.bytes_le[1], guid.bytes_le[0],
                                                 guid.bytes_le[7], guid.bytes_le[6],
                                                 guid.bytes_le[5], guid.bytes_le[4],
                                                 guid.bytes_le[3], guid.bytes_le[2],
                                                 guid.bytes_le[1], guid.bytes_le[0]))

                    buffer = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                    result = ctypes.windll.shell32.SHGetKnownFolderPath(guid_struct, 0, None, buffer)

                    if result == 0:
                        return Path(buffer.value)
                except Exception:
                    pass

                # Fallback
                user_profile = os.environ.get("USERPROFILE")
                if user_profile:
                    p = Path(user_profile) / folder_name
                    if p.exists():
                        return p
                return Path.home() / folder_name

            # Determine path based on intent
            if "desktop" in intent.lower():
                folder_path = get_known_folder_path("Desktop")
            elif "documents" in intent.lower():
                folder_path = get_known_folder_path("Documents")
            elif "downloads" in intent.lower():
                folder_path = get_known_folder_path("Downloads")
            else:
                folder_path = Path.home() / "Desktop"

            path = str(folder_path / filename) if not Path(filename).is_absolute() else filename
            steps.append(TaskStep(
                len(steps) + 1, f"Save as {filename}", "write_file",
                {"path": path, "content": text or "Hello from ALICE"}
            ))

        return steps

    def _plan_search_files(self, intent: str) -> List[TaskStep]:
        """Extract a filename/folder query and optional known-folder scope."""
        import re
        from alice.core.config import get_windows_known_folder

        match = re.search(
            r"(?:where is|locate|find|look for|search for)\\s+(?:the\\s+)?(.+?)\\s*$",
            intent, flags=re.IGNORECASE
        )
        query = match.group(1).strip() if match else intent.strip()
        query = re.sub(r"\\s+(?:folder|directory|file)$", "", query, flags=re.IGNORECASE).strip()
        query = query.strip("\\\"'").strip()
        folder = None
        lowered = intent.lower()
        for label in ("desktop", "documents", "downloads"):
            if label in lowered:
                known = get_windows_known_folder(label.title())
                if known:
                    folder = str(known)
                break
        return [TaskStep(1, f"Search for {query}", "search_files", {"query": query, "folder": folder})]

    def _plan_create(self, intent: str) -> List[TaskStep]:
        """Plan creating folders and files."""
        import re
        import os

        # Extract folder/file name from intent
        # Priority 1: Pattern "create folder/file called X" or "create folder called X anywhere"
        # This handles "Create a folder called Physics Notes on my Desktop"
        name_match = re.search(
            r'(?:folder|file)\s+(?:called\s+|\'c\s+|\'c[,.]?\s+|\'?\s+)?["\']?((?:[^"\'.,\s]+\s*){1,5})["\']?',
            intent, re.IGNORECASE
        )

        if name_match:
            name = name_match.group(1).strip().strip('"\'').strip()
            # Remove trailing location words that might have been captured
            for stop_word in ['on my', 'on', 'in my', 'in', 'on the', 'desktop', 'documents', 'downloads']:
                if name.lower().endswith(stop_word):
                    name = name[:-len(stop_word)].strip()
        else:
            # Try pattern: "create [something] folder" or "make [something] folder"
            alt_match = re.search(r'(?:create|make)\s+([^\s"\']+?)\s+(?:folder|file|directory)', intent, re.IGNORECASE)
            if alt_match:
                name = alt_match.group(1)
            else:
                # Try pattern: "create folder [name]" - more direct pattern
                direct_match = re.search(r'(?:create|make)\s+(?:folder|file)\s+(?:called\s+|\'c\s+|\'c[,.]?\s+|\'?\s*)["\']?((?:[^"\'.,\s]+\s*){1,5})["\']?', intent, re.IGNORECASE)
                if direct_match:
                    name = direct_match.group(1).strip().strip('"\'').strip()
                    # Remove trailing location words
                    for stop_word in ['on my', 'on', 'in my', 'in', 'on the', 'desktop', 'documents', 'downloads']:
                        if name.lower().endswith(stop_word):
                            name = name[:-len(stop_word)].strip()
                else:
                    # Try pattern: "create X on my Desktop" or "create X in Documents"
                    context_match = re.search(r'(?:create|make)\s+(.+?)\s+(?:on\s+my\s+)?(?:desktop|documents|downloads)', intent, re.IGNORECASE)
                    if context_match:
                        name = context_match.group(1).strip()
                    else:
                        # Last resort: extract path from intent directly (for backward compatibility)
                        name = intent.replace("create", "").replace("make", "").strip()

        # Check if it's a file (has extension) or folder
        if "." in name and not name.endswith(("/", os.sep)):
            # It's a file
            from pathlib import Path
            file_path = Path(name)
            parent = file_path.parent

            # Check for folder context (e.g., "on my Desktop", "in Documents")
            folder_context = None
            desktop_match = re.search(r'(?:desktop|on\s+my\s+desktop)', intent, re.IGNORECASE)
            docs_match = re.search(r'(?:documents|doc|my\s+documents)', intent, re.IGNORECASE)
            downloads_match = re.search(r'(?:downloads|my\s+downloads)', intent, re.IGNORECASE)

            if desktop_match:
                from alice.core.config import get_windows_known_folder
                folder_context = get_windows_known_folder("Desktop")
            elif docs_match:
                from alice.core.config import get_windows_known_folder
                folder_context = get_windows_known_folder("Documents")
            elif downloads_match:
                from alice.core.config import get_windows_known_folder
                folder_context = get_windows_known_folder("Downloads")

            steps = []

            # Determine parent directory
            if file_path.is_absolute():
                target_path = file_path
            else:
                if folder_context:
                    target_path = folder_context / file_path.name
                elif parent.name and str(parent) != ".":
                    # Use the extracted parent from the name
                    target_path = file_path
                else:
                    # Default to Desktop
                    from alice.core.config import get_windows_known_folder
                    desktop = get_windows_known_folder("Desktop")
                    target_path = desktop / file_path.name if desktop else Path.home() / "Desktop" / file_path.name

            # Create parent directory if needed
            actual_parent = target_path.parent
            if actual_parent.name and str(actual_parent) != ".":
                steps.append(TaskStep(
                    len(steps) + 1, f"Create folder {actual_parent.name}", "create_folder",
                    {"path": str(actual_parent)}
                ))

            steps.append(TaskStep(
                len(steps) + 1, f"Create file {target_path.name}", "write_file",
                {"path": str(target_path), "content": ""}
            ))
            return steps
        else:
            # It's a folder - determine the full path
            from pathlib import Path
            from alice.core.config import get_windows_known_folder
            folder_name = Path(name).name if name else "NewFolder"

            # Check for location context FIRST
            folder_context = None
            desktop_match = re.search(r'(?:desktop|on\s+my\s+desktop)', intent, re.IGNORECASE)
            docs_match = re.search(r'(?:documents|doc|my\s+documents)', intent, re.IGNORECASE)
            downloads_match = re.search(r'(?:downloads|my\s+downloads)', intent, re.IGNORECASE)

            if desktop_match:
                folder_context = get_windows_known_folder("Desktop")
            elif docs_match:
                folder_context = get_windows_known_folder("Documents")
            elif downloads_match:
                folder_context = get_windows_known_folder("Downloads")

            # Build full path based on context
            if folder_context:
                full_path = folder_context / folder_name
            elif Path(name).is_absolute():
                full_path = Path(name)
            else:
                # Default to Desktop if no context found
                folder_context = get_windows_known_folder("Desktop")
                full_path = folder_context / folder_name if folder_context else Path(name)

            return [
                TaskStep(
                    1, f"Create folder {folder_name}",
                    "create_folder", {"path": str(full_path)}
                )
            ]

    def _plan_extract_zip(self, intent: str) -> List[TaskStep]:
        """Plan ZIP extraction."""
        return [
            TaskStep(
                1, "Extract ZIP",
                "extract_zip", {"archive_path": intent}
            )
        ]

    def _plan_browser_search(self, intent: str) -> List[TaskStep]:
        """Plan a browser search using only the requested search terms."""
        import re

        match = re.search(
            r"\bsearch(?:\s+the\s+web)?\s+for\s+(.+?)(?:\s+in\s+(?:chrome|google\s+chrome))?[.!?]*$",
            intent,
            flags=re.IGNORECASE | re.DOTALL
        )
        query = match.group(1).strip() if match else intent.strip()
        if len(query) >= 2 and query[0] == query[-1] and query[0] in {"'", '"'}:
            query = query[1:-1].strip()
        return [
            TaskStep(1, f"Search Google for {query}", "browser_open",
                     {"search": query, "visible": True})
        ]

    def _plan_browser_extract(self, intent: str) -> List[TaskStep]:
        """Plan browser content extraction."""
        import re
        # Extract URL from intent
        url_match = re.search(r'https?://[^\s]+', intent)
        if url_match:
            url = url_match.group(0)
        else:
            # Try to extract search query
            url = "https://www.google.com/search?q=" + intent.replace("extract ", "").replace("summarize ", "").strip()

        return [
            TaskStep(
                1, f"Extract content from {url}",
                "browser_extract", {"url": url}
            )
        ]

    def _plan_browser_download(self, intent: str) -> List[TaskStep]:
        """Plan browser file download."""
        import re
        url_match = re.search(r'https?://[^\s]+', intent)
        if url_match:
            url = url_match.group(0)
        else:
            url = intent.replace("download ", "").strip()

        return [
            TaskStep(
                1, f"Download file from {url}",
                "browser_download", {"url": url},
                requires_confirmation=True  # Downloads require confirmation (Category B)
            )
        ]

    def _plan_browser_screenshot(self, intent: str) -> List[TaskStep]:
        """Plan browser screenshot."""
        import re
        url_match = re.search(r'https?://[^\s]+', intent)
        if url_match:
            url = url_match.group(0)
        else:
            url = intent.replace("screenshot ", "").replace("capture ", "").strip()

        return [
            TaskStep(
                1, f"Take screenshot of {url}",
                "browser_screenshot", {"url": url}
            )
        ]

    def _plan_general_help(self, intent: str) -> List[TaskStep]:
        """Plan general help request."""
        return [
            TaskStep(
                1, "General help",
                "general", {"intent": intent}
            )
        ]

    def execute_steps(self, tool_executor) -> List[TaskStep]:
        """Execute all planned steps sequentially."""
        results = []
        for step in self.steps:
            logger.info(f"Executing step {step.step_id}: {step.description}")
            success = step.execute(tool_executor)

            if success:
                success = step.verify()
                if not success:
                    logger.warning(f"Step {step.step_id} verification failed")
            else:
                logger.error(f"Step {step.step_id} execution failed: {step.error}")

            results.append(step)
        return results

    def get_plan_summary(self) -> str:
        """Get a summary of the execution plan."""
        if not self.steps:
            return "No plan available."

        summary = f"Plan with {len(self.steps)} step(s):\n"
        for step in self.steps:
            summary += f"  {step.step_id}. {step.description}\n"
        return summary


if __name__ == "__main__":
    from alice.tools.tools import create_default_tools
    registry = create_default_tools()
    planner = TaskPlanner(registry)

    # Test planning
    test_intents = [
        "Open Chrome",
        "Open my FocusFlow project",
        "Find the latest PDF I downloaded",
        "Create a folder called Physics Notes on my Desktop",
    ]

    for intent in test_intents:
        steps = planner.plan(intent)
        print(f"\nIntent: {intent}")
        print(planner.get_plan_summary())

    # Test execution
    print("\n--- Executing steps ---")
    steps = planner.plan("Open Chrome")
    for step in planner.execute_steps(registry):
        print(f"Step {step.step_id}: {step.description}")
        print(f"  Result: {step.result}")
        print(f"  Verified: {step.verified}")