#!/usr/bin/env python3
"""
Natural Language Task Planner for ALICE.
Breaks down user requests into ordered steps, identifies dependencies,
and executes them with verification.
"""

import logging
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
        """Break down user intent into ordered steps."""
        steps = []

        intent_lower = user_intent.lower()

        # Detect intent type and break down accordingly
        if any(kw in intent_lower for kw in ["open", "launch", "start"]):
            steps.extend(self._plan_open_app(user_intent))
        elif any(kw in intent_lower for kw in ["download "]):
            steps.extend(self._plan_browser_download(user_intent))
        elif any(kw in intent_lower for kw in ["screenshot", "capture "]):
            steps.extend(self._plan_browser_screenshot(user_intent))
        elif any(kw in intent_lower for kw in ["extract from ", "summarize ", "read page", "get content"]):
            steps.extend(self._plan_browser_extract(user_intent))
        elif any(kw in intent_lower for kw in ["browser", "search chrome", "search web", "search for "]):
            steps.extend(self._plan_browser_search(user_intent))
        elif any(kw in intent_lower for kw in ["find", "look for"]):
            steps.extend(self._plan_search_files(user_intent))
        elif any(kw in intent_lower for kw in ["create", "make"]):
            steps.extend(self._plan_create(user_intent))
        elif any(kw in intent_lower for kw in ["extract", "unzip"]):
            steps.extend(self._plan_extract_zip(user_intent))
        elif any(kw in intent_lower for kw in ["help", "explain"]):
            steps.extend(self._plan_general_help(user_intent))
        else:
            # Default: ask for clarification
            steps.append(TaskStep(
                1, user_intent,
                "general", {"intent": user_intent},
                requires_confirmation=True
            ))

        self.steps = steps
        return steps

    def _extract_app_name(self, intent: str) -> str:
        """Extract application name from user intent."""
        intent = intent.lower().strip()
        # Remove common prefixes
        for prefix in ["open ", "launch ", "start "]:
            if intent.startswith(prefix):
                intent = intent[len(prefix):]
                break

        # If intent contains commas or clauses like "open notepad, type ...", take the first part
        for sep in [",", " and ", " then "]:
            if sep in intent:
                intent = intent.split(sep)[0]
                break

        return intent.strip()

    def _plan_open_app(self, intent: str) -> List[TaskStep]:
        """Plan opening an application."""
        import re
        app_name = self._extract_app_name(intent)
        steps = [
            TaskStep(
                1, f"Open {app_name}",
                "open_app", {"app_name": app_name}
            )
        ]

        # Check if intent includes typing text
        # Match both quoted: type 'text' and unquoted: type text
        text = None
        type_match = re.search(r"type\s+'([^']+)'", intent)
        if type_match:
            text = type_match.group(1)
        else:
            # Try unquoted format: "type <something> , save as" pattern
            unquoted_match = re.search(r'type\s+([a-zA-Z\s\.\!\?]+?)(?:,\s*save|\s+,\s*save|\s+and\s+save)', intent)
            if unquoted_match:
                text = unquoted_match.group(1).strip().rstrip(',')

        if text:
            # Focus the app before typing
            steps.append(TaskStep(
                2, f"Focus {app_name}",
                "focus_app", {"app_name": app_name}
            ))
            steps.append(TaskStep(
                3, f"Type '{text}'",
                "type_text", {"text": text}
            ))

        # Check if intent includes saving
        save_match = re.search(r'save\s+as\s+([^\s,]+)', intent)
        if save_match:
            filename = save_match.group(1)
            # Expand user paths like ~ or %USERPROFILE%
            from pathlib import Path
            if "desktop" in intent.lower() or "desktop" in filename.lower():
                path = str(Path.home() / "Desktop" / filename)
            else:
                path = filename

            # Get the text that was typed (if any) to use as content
            if text:
                content = text
            else:
                # Default content for saving
                content = "Hello from ALICE"

            # Determine step number based on whether we added focus/type steps
            if text:
                step_num = 4  # Open, Focus, Type, Save
            else:
                step_num = 2  # Open, Save

            steps.append(TaskStep(
                step_num, f"Save as {filename}",
                "save_file", {"path": path, "content": content}
            ))

        return steps

    def _plan_search_files(self, intent: str) -> List[TaskStep]:
        """Plan searching for files."""
        return [
            TaskStep(
                1, "Search files",
                "search_files", {"query": intent}
            )
        ]

    def _plan_create(self, intent: str) -> List[TaskStep]:
        """Plan creating folders/files."""
        return [
            TaskStep(
                1, "Create folder/file",
                "create_folder", {"path": intent}
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
        """Plan browser search."""
        return [
            TaskStep(
                1, "Browser search",
                "browser_open", {"search": intent}
            )
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