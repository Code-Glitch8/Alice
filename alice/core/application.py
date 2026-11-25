#!/usr/bin/env python3
"""Main ALICE application composition root."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from alice.ai.lmstudio_adapter import LMStudioAdapter
from alice.ai.runtime_manager import RuntimeManager
from alice.tools.tools import create_default_tools
from alice.planner.planner import TaskPlanner

logger = logging.getLogger(__name__)


class AliceApplication:
    """Owns the runtime adapter and exposes a single AI lifecycle to the app."""

    def __init__(self, config: Any):
        self.config = config
        self.running = False
        self.initialized = False
        self.ai_adapter = LMStudioAdapter(config)
        self.runtime = RuntimeManager(self.ai_adapter, config)

        # Tool system
        self.tool_registry = create_default_tools()
        self.task_planner = TaskPlanner(self.tool_registry)

        # Permission system
        self.automation_config = config.automation

        # System prompt that enables tool calling
        self.system_prompt = """You are ALICE, a helpful local Windows desktop assistant.
You have access to tools for controlling the computer. When the user asks you to perform an action on their computer,
you should use the appropriate tool by calling it.

Available tools:
- open_app: Open an application (e.g., "notepad", "chrome", "calculator")
- close_app: Close an application
- focus_app: Focus an application window
- create_folder: Create a folder
- search_files: Search for files
- browser_open: Open browser or search the web
- browser_extract: Extract text content from a web page
- browser_download: Download a file from the web
- browser_screenshot: Take a screenshot of a web page
- type_text: Type text into the active window
- keyboard_shortcut: Execute a keyboard shortcut (e.g., "ctrl+c", "alt+tab")
- mouse_move: Move mouse to coordinates
- mouse_click: Click mouse
- mouse_scroll: Scroll mouse wheel
- select_text: Select text (all, word, line, paragraph)
- copy_paste: Copy, cut, or paste
- get_clipboard: Get clipboard content
- set_clipboard: Set clipboard content
- emergency_stop: Emergency stop all automation
- system_info: Get system information
- list_running_apps: List running applications

When you need to use a tool, respond with a JSON object:
{
  "tool_calls": [
    {
      "id": "call_1",
      "type": "function",
      "function": {"name": "tool_name", "arguments": "{\"param\": \"value\"}"}
    }
  ]
}

Only call tools when the user explicitly requests a computer action. For normal conversation, respond normally without tool calls."""

    async def initialize(self) -> bool:
        """Initialize the local AI server connection without loading the model."""
        if self.initialized:
            return True
        ok = await self.runtime.start()
        self.initialized = bool(ok)
        self.running = bool(ok)
        return bool(ok)

    async def ask(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send one prompt to the configured local model."""
        if not self.initialized and not await self.initialize():
            raise RuntimeError(self.ai_adapter.last_error or "LM Studio is unavailable")

        sp = system_prompt or self.system_prompt
        return await self.runtime.chat([
            {"role": "system", "content": sp},
            {"role": "user", "content": prompt},
        ])

    async def chat_with_tools(self, history: List[Dict[str, str]]) -> str:
        """Chat with tool calling support."""
        if not self.initialized and not await self.initialize():
            raise RuntimeError(self.ai_adapter.last_error or "LM Studio is unavailable")

        # Prepare messages with system prompt
        messages = [{"role": "system", "content": self.system_prompt}] + history

        # Get response from LLM
        response = await self.runtime.chat(messages)

        # Check if response contains tool calls
        try:
            parsed = json.loads(response)
            if "tool_calls" in parsed:
                return await self._execute_tool_calls(parsed["tool_calls"], history)
        except json.JSONDecodeError:
            # Not a tool call, return as-is
            return response

        return response

    async def _execute_tool_calls(self, tool_calls: List[Dict], history: List[Dict[str, str]]) -> str:
        """Execute tool calls and return results to LLM for final response."""
        tool_results = []

        for call in tool_calls:
            if call.get("type") != "function":
                continue

            func = call.get("function", {})
            tool_name = func.get("name")
            arguments_str = func.get("arguments", "{}")
            call_id = call.get("id", "call_1")

            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}

            # Check permissions
            tool = self.tool_registry.get(tool_name)
            if tool:
                if not self._check_permission(tool):
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"Permission denied for tool {tool_name} (category {tool.required_permission})"
                    })
                    continue

            # Execute tool
            if tool:
                result = tool.execute(**arguments)
            else:
                result = {"status": "error", "error": f"Tool {tool_name} not found"}

            tool_results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result)
            })

        # Send tool results back to LLM for final response
        messages = [{"role": "system", "content": self.system_prompt}] + history + [
            {"role": "assistant", "content": json.dumps({"tool_calls": tool_calls})}
        ] + tool_results

        final_response = await self.runtime.chat(messages)
        return final_response

    def _check_permission(self, tool) -> bool:
        """Check if tool execution is permitted based on automation config."""
        perm = tool.required_permission

        if perm == "A":
            return self.automation_config.auto_confirm_category_a
        elif perm == "B":
            return not self.automation_config.require_confirm_category_b  # True means requires confirmation
        elif perm == "C":
            return not self.automation_config.restricted_category_c  # True means restricted
        return True

    async def execute_intent(self, user_intent: str) -> Dict[str, Any]:
        """Execute a user intent using the task planner."""
        steps = self.task_planner.plan(user_intent)

        # Check permissions and execute steps sequentially
        results = []
        for step in steps:
            tool = self.tool_registry.get(step.tool_name)
            if tool:
                # Check if step requires confirmation
                if not self._check_permission(tool):
                    step.requires_confirmation = True
                    results.append({
                        "step_id": step.step_id,
                        "description": step.description,
                        "tool": step.tool_name,
                        "requires_confirmation": True,
                        "message": f"Step requires user confirmation (category {tool.required_permission})"
                    })
                    break  # Stop for confirmation

            success = step.execute(self.tool_registry)
            if success:
                # Verify step result
                if step.result:
                    if isinstance(step.result, dict):
                        step.verified = step.result.get("status") == "success"
                    else:
                        step.verified = bool(step.result)
            else:
                step.verified = False

            results.append({
                "step_id": step.step_id,
                "description": step.description,
                "tool": step.tool_name,
                "result": step.result,
                "verified": step.verified,
                "error": step.error,
                "requires_confirmation": False
            })

        return {
            "plan": self.task_planner.get_plan_summary(),
            "steps": results
        }

    async def shutdown_async(self) -> None:
        if self.initialized:
            await self.runtime.stop()
        self.initialized = False
        self.running = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "initialized": self.initialized,
            "running": self.running,
            "ai": self.runtime.get_status(),
            "tools": [t.name for t in self.tool_registry.list_tools()],
        }

    def run(self) -> None:
        """Start the local runtime service; GUI wiring is a later integration phase."""
        self.running = asyncio.run(self.initialize())
        if not self.running:
            raise RuntimeError(self.ai_adapter.last_error or "Could not initialize ALICE runtime")
        logger.info("ALICE runtime initialized. The Qwen model remains unloaded until needed.")

    def shutdown(self) -> None:
        import asyncio
        if self.initialized:
            asyncio.run(self.shutdown_async())
        self.running = False
