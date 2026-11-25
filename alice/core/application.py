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
- open_app(app_name: string): Open an application (e.g., "notepad", "chrome", "calculator")
- close_app(app_name: string): Close an application
- focus_app(app_name: string): Focus an application window
- create_folder(path: string): Create a folder
- search_files(query: string, folder?: string): Search for files by name or content
- browser_open(url?: string, search?: string): Open browser or search the web
- browser_extract(url: string, selector?: string): Extract text content from a web page
- browser_download(url: string, destination?: string): Download a file from the web
- browser_screenshot(url: string, full_page?: boolean, destination?: string): Take a screenshot of a web page
- type_text(text: string, delay?: number): Type text into the active window
- keyboard_shortcut(keys: string): Execute a keyboard shortcut (e.g., "ctrl+c", "alt+tab")
- mouse_move(x: number, y: number, duration?: number): Move mouse to coordinates
- mouse_click(x?: number, y?: number, button?: string, clicks?: number): Click mouse
- mouse_scroll(clicks: number, x?: number, y?: number): Scroll mouse wheel
- select_text(method?: string): Select text (all, word, line, paragraph)
- copy_paste(action: string): Copy, cut, or paste (copy, cut, paste)
- get_clipboard(): Get clipboard content
- set_clipboard(content: string): Set clipboard content
- emergency_stop(): Emergency stop all automation
- system_info(): Get system information
- list_running_apps(): List running applications

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
                # Extract content from the AI response (may be None/empty when only tool_calls)
                content = parsed.get("content")
                if content is None:
                    content = ""
                return await self._execute_tool_calls(parsed["tool_calls"], history, content)
        except json.JSONDecodeError:
            # Not a tool call, return as-is
            return response

        return response

    def _normalize_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tool arguments to match tool signatures.

        Handles parameter name aliases that the AI might use.
        """
        if not arguments:
            return arguments

        # Parameter name aliases (AI-generated -> tool signature)
        # These map common alternative names to the actual parameter names
        param_aliases = {
            "open_app": {"app": "app_name"},
            "close_app": {"app": "app_name"},
            "focus_app": {"app": "app_name"},
            "browser_open": {"url": "url", "search": "search"},
            "browser_extract": {"url": "url", "selector": "selector"},
            "browser_download": {"url": "url", "destination": "destination"},
            "browser_screenshot": {"url": "url", "full_page": "full_page", "destination": "destination"},
            "mouse_move": {"x": "x", "y": "y", "duration": "duration"},
            "mouse_click": {"x": "x", "y": "y", "button": "button", "clicks": "clicks"},
            "mouse_scroll": {"clicks": "clicks", "x": "x", "y": "y"},
            "type_text": {"text": "text", "delay": "delay"},
            "keyboard_shortcut": {"keys": "keys"},
            "search_files": {"query": "query", "folder": "folder"},
            "create_folder": {"path": "path"},
            "copy_paste": {"action": "action"},
            "set_clipboard": {"content": "content"},
            "select_text": {"method": "method"},
        }

        normalized = {}
        aliases = param_aliases.get(tool_name, {})

        for key, value in arguments.items():
            # If we have an alias for this tool, use it; otherwise keep the key as-is
            normalized_key = aliases.get(key, key)
            normalized[normalized_key] = value

        return normalized

    async def _execute_tool_calls(self, tool_calls: List[Dict], history: List[Dict[str, str]], assistant_content: str = "") -> str:
        """Execute tool calls and return results to LLM for final response."""
        tool_results = []

        for call in tool_calls:
            if call.get("type") != "function":
                continue

            func = call.get("function", {})
            tool_name = func.get("name")
            arguments_str = func.get("arguments", "{}")
            call_id = call.get("id", "call_1")

            # LM Studio may return function arguments as either a JSON string
            # (OpenAI-compatible wire format) or an already-decoded dictionary.
            # Never pass a dict to json.loads(), and never silently execute a
            # malformed/non-object argument payload with empty arguments.
            if isinstance(arguments_str, dict):
                arguments = arguments_str
            elif isinstance(arguments_str, str):
                try:
                    arguments = json.loads(arguments_str or "{}")
                except json.JSONDecodeError as exc:
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({
                            "status": "error",
                            "error": f"Invalid JSON arguments for {tool_name}: {exc}"
                        })
                    })
                    continue
            elif arguments_str is None:
                arguments = {}
            else:
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps({
                        "status": "error",
                        "error": f"Unsupported argument type for {tool_name}: {type(arguments_str).__name__}"
                    })
                })
                continue

            if not isinstance(arguments, dict):
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps({
                        "status": "error",
                        "error": f"Arguments for {tool_name} must be a JSON object, got {type(arguments).__name__}"
                    })
                })
                continue

            # Normalize parameter names to match tool signatures
            arguments = self._normalize_tool_arguments(tool_name, arguments)

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
        # Use OpenAI-compatible format: tool_calls at message level, not inside content
        # Ensure arguments are properly formatted as JSON strings for the API
        formatted_tool_calls = []
        for tc in tool_calls:
            formatted_call = {
                "id": tc.get("id"),
                "type": tc.get("type"),
                "function": {
                    "name": tc.get("function", {}).get("name"),
                    "arguments": tc.get("function", {}).get("arguments", {})
                }
            }
            # Ensure arguments are a JSON string (OpenAI format)
            if isinstance(formatted_call["function"]["arguments"], dict):
                formatted_call["function"]["arguments"] = json.dumps(formatted_call["function"]["arguments"])
            formatted_tool_calls.append(formatted_call)

        if assistant_content:
            # Assistant has both content and tool calls
            assistant_message = {"role": "assistant", "content": assistant_content, "tool_calls": formatted_tool_calls}
        else:
            # Assistant only has tool calls (no text content)
            # Use empty string for content when only tool_calls are present
            assistant_message = {"role": "assistant", "content": "", "tool_calls": formatted_tool_calls}

        messages = [{"role": "system", "content": self.system_prompt}] + history + [
            assistant_message
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
