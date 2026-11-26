#!/usr/bin/env python3
"""Main ALICE application composition root."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from alice.ai.lmstudio_adapter import LMStudioAdapter, LMStudioError
from alice.ai.runtime_manager import RuntimeManager
from alice.tools.tools import create_default_tools, ToolDispatcher, Tool
from alice.planner.planner import TaskPlanner, TaskStep

logger = logging.getLogger(__name__)


class AliceApplication:
    """Owns the runtime adapter and exposes a single AI lifecycle to the app."""

    def __init__(self, config: Any):
        self.config = config
        self.running = False
        self.initialized = False
        self.ai_adapter = LMStudioAdapter(config)
        self.runtime = RuntimeManager(self.ai_adapter, config)

        # Tool system with centralized dispatcher
        self.tool_registry = create_default_tools()
        self.task_planner = TaskPlanner(self.tool_registry)
        # Central tool dispatcher - all tool execution goes through this
        self.tool_dispatcher = ToolDispatcher(self.tool_registry, config)

        # Permission system
        self.automation_config = config.automation
        self.max_tool_calls = 5  # Prevent infinite loops
        self.current_tool_call_count = 0

        # System prompt for fallback text-based tool calling
        self.system_prompt = """You are ALICE, a helpful local Windows desktop assistant.
You have access to tools for controlling the computer. When the user asks you to perform an action on their computer, you should use the appropriate tool by calling it.

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
- close_all_apps(): Close all applications opened by ALICE
- get_open_apps(): List applications opened by ALICE
- get_app_status(app_name: string): Get status of a specific application

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

    async def chat_with_tools(self, history: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> str:
        """Chat with the model and execute tool calls until a final answer is produced.

        Tool results are fed back through this single bounded loop. If Qwen emits
        reasoning without a user-facing answer, ALICE attempts a deterministic
        plan from the user's actual request rather than claiming the action ran.
        """
        if not self.initialized and not await self.initialize():
            raise RuntimeError(self.ai_adapter.last_error or "LM Studio is unavailable")

        messages = [{"role": "system", "content": self.system_prompt}] + [dict(item) for item in history]
        tool_definitions = tools if tools is not None else self.get_tools_for_api()
        max_rounds = max(1, int(getattr(self.automation_config, "max_tool_calls", 5) or 5))
        self.current_tool_call_count = 0
        self.tool_dispatcher.call_count = 0

        for round_count in range(1, max_rounds + 1):
            try:
                response = await self.runtime.chat(messages, tools=tool_definitions)
            except LMStudioError as exc:
                error_text = str(exc)
                if "empty user-facing answer" not in error_text.lower():
                    raise
                user_content = self._get_user_message(history) or ""
                logger.warning("Model returned no user-facing content; trying safe planner fallback for the original request.")
                return await self._execute_planned_tasks(history, user_content, [])

            response_text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
            parsed_response = self._parse_ai_response(response_text)

            native_tool_calls: List[Dict[str, Any]] = []
            content = ""
            if isinstance(parsed_response, dict):
                calls = parsed_response.get("tool_calls", [])
                if isinstance(calls, list):
                    native_tool_calls = calls
                raw_content = parsed_response.get("content")
                content = raw_content.strip() if isinstance(raw_content, str) else ""
            elif isinstance(parsed_response, str):
                content = parsed_response.strip()
            elif parsed_response is None:
                # Only use the raw response as visible text when parsing did not
                # identify a structured tool-call envelope.
                content = self._remove_xml_markup(response_text).strip() if "<function" in response_text else response_text.strip()

            # Normalize IDs and wire-format arguments once, before both execution
            # and adding the assistant tool-call message to conversation history.
            normalized_calls: List[Dict[str, Any]] = []
            seen_ids = set()
            for index, call in enumerate(native_tool_calls):
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict) or not function.get("name"):
                    continue
                call_id = call.get("id") or f"alice_{round_count}_{index}"
                if call_id in seen_ids:
                    continue
                seen_ids.add(call_id)
                arguments = function.get("arguments", "{}")
                if isinstance(arguments, dict):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                elif not isinstance(arguments, str):
                    arguments = json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)
                normalized_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {"name": function["name"], "arguments": arguments}
                })

            if normalized_calls:
                user_content = self._get_user_message(history) or content
                if self._is_compound_command(user_content, normalized_calls):
                    return await self._execute_planned_tasks(history, user_content, normalized_calls)

                tool_results = await self._execute_tool_calls(normalized_calls, messages, content)
                messages.append({
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": normalized_calls
                })
                messages.extend(tool_results)
                continue

            if content:
                return content

            # An empty turn with no tool call must never be reported as success.
            user_content = self._get_user_message(history) or ""
            if user_content:
                fallback = await self._execute_planned_tasks(history, user_content, [])
                if not fallback.lower().startswith("alice could not safely map"):
                    return fallback
            return "The model returned an empty reply. No desktop action was performed."

        return (
            f"ALICE stopped after {max_rounds} model/tool rounds to prevent an endless loop. "
            "The last tool results are available in the conversation; ask to continue."
        )

    def _get_user_message(self, history: List[Dict[str, str]]) -> Optional[str]:
        """Get the most recent user message from conversation history.

        Args:
            history: List of message dicts with 'role' and 'content' keys

        Returns:
            The most recent user message content, or None if not found
        """
        if not history:
            return None
        # Get the last user message
        for msg in reversed(history):
            if msg.get("role") == "user":
                return msg.get("content")
        return None

    def _remove_xml_markup(self, content: str) -> str:
        """Remove XML-style tool call markup from content."""
        import re
        # Remove <function...>...</function> blocks
        content = re.sub(r'<function[^>]*>.*?</function>', '', content, flags=re.DOTALL)
        # Clean up artifacts like \n and ```
        content = re.sub(r'\\n\s*\n?', '', content)
        content = content.strip()
        # Remove empty code block markers
        content = re.sub(r'```\s*```', '', content)
        return content.strip()

    def _is_compound_command(self, content: str, tool_calls: List[Dict]) -> bool:
        """Detect if this is a compound command that needs planning.

        Compound commands contain multiple actions like "open X and do Y" or
        sequential operations that need proper ordering.
        """
        # Check tool call count - multiple calls may indicate compound command
        if len(tool_calls) > 1:
            return True

        # Check content for compound command patterns
        if content:
            content_lower = content.lower()
            compound_patterns = [
                "and ", " then ", " after ", " followed by ",
                " open ",
                " type ",
                " create ",
                " download ",
            ]
            if any(pattern in content_lower for pattern in compound_patterns):
                # Single tool call with compound intent - planner may help
                return True

        return False

    async def _execute_planned_tasks(self, history: List[Dict[str, str]], content: str, tool_calls: List[Dict]) -> str:
        """Execute a deterministic plan through the same permission-aware dispatcher."""
        latest_user = self._get_user_message(history) or content or ""
        steps = self.task_planner.plan(latest_user)
        if not steps or any(step.tool_name == "general" for step in steps):
            return (
                "ALICE could not safely map the request to a supported desktop action. "
                "No application or text action was performed."
            )

        self.tool_dispatcher.call_count = 0
        results = []
        for step in steps:
            tool = self.tool_registry.get(step.tool_name)
            if tool is None:
                results.append({
                    "step": step.description, "tool": step.tool_name,
                    "status": "error", "message": f"Tool '{step.tool_name}' is not registered."
                })
                break

            if not self._check_permission(tool):
                step.requires_confirmation = True
                results.append({
                    "step": step.description, "tool": step.tool_name,
                    "status": "blocked",
                    "message": (
                        f"Category {tool.required_permission} permission is not enabled. "
                        "No action was taken for this step."
                    )
                })
                break

            try:
                result = await self.tool_dispatcher.execute_async(step.tool_name, step.parameters)
            except Exception as exc:
                result = {"status": "error", "error": str(exc)}
            step.result = result
            status = result.get("status") if isinstance(result, dict) else None
            step.verified = status in {"success", "navigated", "search_completed", "completed"}
            results.append({
                "step": step.description,
                "tool": step.tool_name,
                "status": "success" if step.verified else "error",
                "message": (
                    (result.get("message") or result.get("error") or str(result))
                    if isinstance(result, dict) else str(result)
                )
            })
            # Stop dependent work if opening/focusing the target application failed.
            if not step.verified:
                break

        succeeded = sum(1 for item in results if item["status"] == "success")
        lines = [f"Completed {succeeded} of {len(steps)} planned step(s)."]
        lines.extend(f"- {item['step']}: {item['message']}" for item in results)
        if results and results[-1]["status"] == "blocked":
            lines.append("ALICE stopped because this action requires permission; it did not claim the step was completed.")
        elif succeeded < len(steps):
            lines.append("ALICE stopped after a failed step; dependent actions were not attempted.")
        return "\n".join(lines)

    def _parse_ai_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse AI response, handling multiple formats.

        AI may return:
        - Raw JSON: {"tool_calls": [...], "content": "..."}
        - Markdown-fenced: ```json\n{"tool_calls": [...]}\n```
        - XML-style (Qwen): <function=type_name>\n<parameter>name</parameter>\n</function>
        - has_tool_calls format from LM Studio

        Also handles the new format from LM Studio with has_tool_calls flag.
        When tool_calls array is empty but content contains XML, extracts XML calls.
        Normalizes dict arguments to JSON strings for consistency.
        """
        if not response:
            return None

        response = response.strip()

        # Try raw JSON parsing first (handles has_tool_calls format)
        json_result = None
        try:
            json_result = json.loads(response)
        except json.JSONDecodeError:
            pass

        if json_result is not None:
            # Check for has_tool_calls format from LM Studio
            if json_result.get("has_tool_calls") or "tool_calls" in json_result:
                parsed = json_result
                tool_calls = parsed.get("tool_calls", [])
                content = parsed.get("content")

                # Normalize dict arguments to JSON strings
                normalized_tool_calls = []
                for tc in tool_calls:
                    if isinstance(tc, dict) and "function" in tc:
                        func = tc.get("function", {})
                        args = func.get("arguments", {})
                        # Normalize args to JSON string if it's a dict
                        if isinstance(args, dict):
                            args = json.dumps(args, ensure_ascii=False)
                        normalized_tool_calls.append({
                            "id": tc.get("id"),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": func.get("name"),
                                "arguments": args
                            }
                        })
                tool_calls = normalized_tool_calls

                result = {
                    "tool_calls": tool_calls,
                    "content": content
                }

                # If tool_calls is empty but content contains XML, extract XML calls
                if not tool_calls and content and isinstance(content, str):
                    xml_calls = self._parse_xml_tool_calls(content)
                    if xml_calls:
                        # Extract clean content (without XML markup)
                        clean_content = self._remove_xml_markup(content)
                        result["tool_calls"] = xml_calls
                        result["content"] = clean_content

                return result

            # JSON response without tool_calls - check if content contains XML
            content = json_result.get("content", "")
            if content and isinstance(content, str) and "<function" in content:
                xml_calls = self._parse_xml_tool_calls(content)
                if xml_calls:
                    clean_content = self._remove_xml_markup(content)
                    return {
                        "tool_calls": xml_calls,
                        "content": clean_content
                    }

            return json_result

        # Check for XML-style tool calls in raw response (Qwen format)
        xml_tool_calls = self._parse_xml_tool_calls(response)
        if xml_tool_calls:
            # Extract content text (without XML markup) if present
            content = self._remove_xml_markup(response)
            return {
                "tool_calls": xml_tool_calls,
                "content": content
            }

        # Try markdown-fenced JSON
        if "```json" in response or "```" in response:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                content = match.group(1).strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass

        return None

    def _parse_xml_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse XML-style tool calls from Qwen model.

        Qwen may return tool calls in XML format:
        <function=type_text>
        <parameter>text</parameter>
        </function>

        Or with name attribute:
        <function=name="open_app"><parameter name="app_name">notepad</parameter></function>

        Returns list of tool call dicts or empty list if not XML format.
        """
        tool_calls = []

        # Match XML tool call patterns
        # Pattern 1: <function=function_name> or <function=name="function_name">
        # Pattern 2: Content with <parameter> elements

        # First, try to match <function=name="..."> format (attribute style)
        attr_pattern = r'<function[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)</function>'
        attr_matches = list(re.finditer(attr_pattern, response, re.DOTALL | re.IGNORECASE))

        for match in attr_matches:
            func_name = match.group(1)
            inner_content = match.group(2)
            args = self._parse_xml_parameters(inner_content, func_name)
            tool_calls.append({
                "id": f"call_{len(tool_calls) + 1}",
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(args, ensure_ascii=False) if args else "{}"
                }
            })

        # Second, try to match <function=function_name> format (direct assignment)
        direct_pattern = r'<function=(\w+)>(.*?)</function>'
        direct_matches = list(re.finditer(direct_pattern, response, re.DOTALL))

        for match in direct_matches:
            func_name = match.group(1)
            inner_content = match.group(2)
            args = self._parse_xml_parameters(inner_content, func_name)
            # Avoid duplicates if a tool was already matched by attribute pattern
            if not any(tc["function"]["name"] == func_name for tc in tool_calls):
                tool_calls.append({
                    "id": f"call_{len(tool_calls) + 1}",
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": json.dumps(args, ensure_ascii=False) if args else "{}"
                    }
                })

        return tool_calls

    def _parse_xml_parameters(self, inner_content: str, func_name: str) -> Dict[str, Any]:
        """Parse parameters from XML function call inner content."""
        args = {}

        # Parse <parameter> elements
        # Handle both <parameter>value</parameter> and <parameter name="key">value</parameter>
        param_pattern = r'<parameter[^>]*>(.*?)</parameter>'
        param_matches = list(re.finditer(param_pattern, inner_content, re.DOTALL))

        if not param_matches:
            return args

        for i, pm in enumerate(param_matches):
            param_value = pm.group(1).strip()

            # Check for name attribute on parameter element
            name_match = re.search(r'name=["\']([^"\']+)["\']', pm.group(0))
            if name_match:
                # Named parameter: <parameter name="text">hello</parameter>
                param_name = name_match.group(1)
                args[param_name] = param_value
            else:
                # For simple tools with single param or positional args
                # Use parameter index as key for single-arg tools
                if i == 0:
                    # Check if this tool has a known single parameter
                    single_param_map = {
                        "type_text": "text",
                        "keyboard_shortcut": "keys",
                        "mouse_move": None,  # needs x and y
                        "set_clipboard": "content",
                        "get_clipboard": None,
                        "open_app": "app_name",
                        "close_app": "app_name",
                        "focus_app": "app_name",
                    }
                    if single_param_map.get(func_name):
                        args[single_param_map[func_name]] = param_value
                    else:
                        # Use generic key
                        args[f"arg{i + 1}"] = param_value
                else:
                    args[f"arg{i + 1}"] = param_value

        return args

    def get_tools_for_api(self) -> List[Dict[str, Any]]:
        """Generate OpenAI-compatible tool definitions from the tool registry.

        This is used to send tool definitions to LM Studio for native function calling.
        """
        tools = []
        for tool in self.tool_registry.list_tools():
            # Get tool signature information
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }

            # Add parameter information based on tool type
            # This is a simplified mapping - in a full implementation we'd inspect
            # the tool's signature
            if tool.name == "open_app":
                tool_def["function"]["parameters"]["properties"] = {
                    "app_name": {"type": "string", "description": "Name of the application to open"},
                    "target_path": {"type": "string", "description": "Optional target path or URL", "default": None}
                }
                tool_def["function"]["parameters"]["required"] = ["app_name"]
            elif tool.name == "close_app":
                tool_def["function"]["parameters"]["properties"] = {
                    "app_name": {"type": "string", "description": "Name of the application to close"}
                }
                tool_def["function"]["parameters"]["required"] = ["app_name"]
            elif tool.name == "focus_app":
                tool_def["function"]["parameters"]["properties"] = {
                    "app_name": {"type": "string", "description": "Name of the application to focus"}
                }
                tool_def["function"]["parameters"]["required"] = ["app_name"]
            elif tool.name == "create_folder":
                tool_def["function"]["parameters"]["properties"] = {
                    "path": {"type": "string", "description": "Path of the folder to create"}
                }
                tool_def["function"]["parameters"]["required"] = ["path"]
            elif tool.name == "search_files":
                tool_def["function"]["parameters"]["properties"] = {
                    "query": {"type": "string", "description": "Search query"},
                    "folder": {"type": "string", "description": "Folder to search in (optional)", "default": None}
                }
                tool_def["function"]["parameters"]["required"] = ["query"]
            elif tool.name == "browser_open":
                tool_def["function"]["parameters"]["properties"] = {
                    "url": {"type": "string", "description": "URL to open", "default": None},
                    "search": {"type": "string", "description": "Search term for web search", "default": None},
                    "visible": {"type": "boolean", "description": "Whether to open browser visibly", "default": False}
                }
            elif tool.name == "browser_extract":
                tool_def["function"]["parameters"]["properties"] = {
                    "url": {"type": "string", "description": "URL to extract content from"},
                    "selector": {"type": "string", "description": "CSS selector (optional)", "default": None},
                    "visible": {"type": "boolean", "description": "Whether to open browser visibly", "default": False}
                }
                tool_def["function"]["parameters"]["required"] = ["url"]
            elif tool.name == "browser_download":
                tool_def["function"]["parameters"]["properties"] = {
                    "url": {"type": "string", "description": "URL of file to download"},
                    "destination": {"type": "string", "description": "Destination path (optional)", "default": None}
                }
                tool_def["function"]["parameters"]["required"] = ["url"]
            elif tool.name == "browser_screenshot":
                tool_def["function"]["parameters"]["properties"] = {
                    "url": {"type": "string", "description": "URL to screenshot"},
                    "full_page": {"type": "boolean", "description": "Capture full page", "default": True},
                    "destination": {"type": "string", "description": "Destination path (optional)", "default": None},
                    "visible": {"type": "boolean", "description": "Whether to open browser visibly", "default": False}
                }
                tool_def["function"]["parameters"]["required"] = ["url"]
            elif tool.name == "type_text":
                tool_def["function"]["parameters"]["properties"] = {
                    "text": {"type": "string", "description": "Text to type"},
                    "delay": {"type": "number", "description": "Delay between keystrokes", "default": 0},
                    "interval": {"type": "number", "description": "Typing interval", "default": 0},
                    "target_window": {"type": "string", "description": "Target window title to type into (optional)", "default": None}
                }
                tool_def["function"]["parameters"]["required"] = ["text"]
            elif tool.name == "keyboard_shortcut":
                tool_def["function"]["parameters"]["properties"] = {
                    "keys": {"type": "string", "description": "Keys to press (e.g., 'ctrl+c', 'alt+tab')"}
                }
                tool_def["function"]["parameters"]["required"] = ["keys"]
            elif tool.name == "mouse_move":
                tool_def["function"]["parameters"]["properties"] = {
                    "x": {"type": "number", "description": "X coordinate"},
                    "y": {"type": "number", "description": "Y coordinate"},
                    "duration": {"type": "number", "description": "Duration in seconds", "default": 0}
                }
                tool_def["function"]["parameters"]["required"] = ["x", "y"]
            elif tool.name == "mouse_click":
                tool_def["function"]["parameters"]["properties"] = {
                    "x": {"type": "number", "description": "X coordinate (optional)", "default": None},
                    "y": {"type": "number", "description": "Y coordinate (optional)", "default": None},
                    "button": {"type": "string", "description": "Button to click ('left', 'right', 'middle')", "default": "left"},
                    "clicks": {"type": "number", "description": "Number of clicks", "default": 1}
                }
            elif tool.name == "mouse_scroll":
                tool_def["function"]["parameters"]["properties"] = {
                    "clicks": {"type": "number", "description": "Number of scroll notches", "default": 3},
                    "x": {"type": "number", "description": "X coordinate (optional)", "default": None},
                    "y": {"type": "number", "description": "Y coordinate (optional)", "default": None}
                }
                tool_def["function"]["parameters"]["required"] = ["clicks"]
            elif tool.name == "select_text":
                tool_def["function"]["parameters"]["properties"] = {
                    "method": {"type": "string", "description": "Selection method ('all', 'word', 'line', 'paragraph')", "default": "all"}
                }
            elif tool.name == "copy_paste":
                tool_def["function"]["parameters"]["properties"] = {
                    "action": {"type": "string", "description": "Action ('copy', 'cut', 'paste')"}
                }
                tool_def["function"]["parameters"]["required"] = ["action"]
            elif tool.name == "get_clipboard":
                tool_def["function"]["parameters"]["properties"] = {}
            elif tool.name == "set_clipboard":
                tool_def["function"]["parameters"]["properties"] = {
                    "content": {"type": "string", "description": "Content to set to clipboard"}
                }
                tool_def["function"]["parameters"]["required"] = ["content"]
            elif tool.name == "system_info":
                tool_def["function"]["parameters"]["properties"] = {}
            elif tool.name == "list_running_apps":
                tool_def["function"]["parameters"]["properties"] = {}
            elif tool.name == "get_app_status":
                tool_def["function"]["parameters"]["properties"] = {
                    "app_name": {"type": "string", "description": "Name of the application"}
                }
                tool_def["function"]["parameters"]["required"] = ["app_name"]
            elif tool.name == "close_all_apps":
                tool_def["function"]["parameters"]["properties"] = {}
            elif tool.name == "get_open_apps":
                tool_def["function"]["parameters"]["properties"] = {}
            elif tool.name == "emergency_stop":
                tool_def["function"]["parameters"]["properties"] = {}

            tools.append(tool_def)

        return tools

    def _normalize_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tool arguments to match tool signatures.

        Handles parameter name aliases that the AI might use.
        """
        if not arguments:
            return arguments

        # Parameter name aliases (AI-generated -> tool signature)
        # These map common alternative names to the actual parameter names
        param_aliases = {
            "open_app": {"app": "app_name", "target": "target_path"},
            "close_app": {"app": "app_name"},
            "focus_app": {"app": "app_name"},
            "browser_open": {"url": "url", "search": "search"},
            "browser_extract": {"url": "url", "selector": "selector"},
            "browser_download": {"url": "url", "destination": "destination"},
            "browser_screenshot": {"url": "url", "full_page": "full_page", "destination": "destination"},
            "mouse_move": {"x": "x", "y": "y", "duration": "duration"},
            "mouse_click": {"x": "x", "y": "y", "button": "button", "clicks": "clicks"},
            "mouse_scroll": {"clicks": "clicks", "x": "x", "y": "y"},
            "type_text": {"text": "text", "delay": "delay", "target_window": "target_window", "window": "target_window"},
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

    async def _execute_tool_calls(self, tool_calls: List[Dict], history: List[Dict[str, str]], assistant_content: str = "") -> List[Dict[str, str]]:
        """Execute one model tool-call round and return its matching tool messages.

        The caller owns the conversation loop and feeds the results back to the
        model. This method deliberately does not make a second model call.
        """
        tool_results: List[Dict[str, str]] = []
        for index, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            tool_name = function.get("name")
            call_id = call.get("id") or f"alice_tool_{index}"
            arguments_value = function.get("arguments", "{}")

            if isinstance(arguments_value, dict):
                arguments = arguments_value
            elif isinstance(arguments_value, str):
                try:
                    arguments = json.loads(arguments_value or "{}")
                except json.JSONDecodeError as exc:
                    tool_results.append({
                        "role": "tool", "tool_call_id": call_id,
                        "content": json.dumps({"status": "error", "error": f"Invalid JSON arguments for {tool_name}: {exc}"})
                    })
                    continue
            elif arguments_value is None:
                arguments = {}
            else:
                tool_results.append({
                    "role": "tool", "tool_call_id": call_id,
                    "content": json.dumps({"status": "error", "error": f"Unsupported arguments type: {type(arguments_value).__name__}"})
                })
                continue

            if not isinstance(arguments, dict):
                tool_results.append({
                    "role": "tool", "tool_call_id": call_id,
                    "content": json.dumps({"status": "error", "error": "Tool arguments must be a JSON object."})
                })
                continue

            arguments = self._normalize_tool_arguments(tool_name, arguments)
            tool = self.tool_registry.get(tool_name)
            if tool is None:
                result = {"status": "error", "error": f"Tool '{tool_name}' not found"}
            elif not self._check_permission(tool):
                result = {
                    "status": "blocked",
                    "error": f"Permission denied for tool {tool_name} (category {tool.required_permission})."
                }
            else:
                result = await self.tool_dispatcher.execute_async(tool_name, arguments)

            tool_results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False, default=str)
            })

        return tool_results

    def _check_permission(self, tool) -> bool:
        """Check if tool execution is permitted based on automation config.

        Returns True if the tool is allowed to execute.
        Category A: auto_confirm_category_a = True allows execution
        Category B: require_confirm_category_b = False allows execution (auto-confirm off = auto-confirm on)
        Category C: restricted_category_c = False allows execution (restricted = blocked by default)
        """
        perm = tool.required_permission

        if perm == "A":
            # Category A tools: auto-confirm enabled means allowed
            return self.automation_config.auto_confirm_category_a
        elif perm == "B":
            # Category B tools: require_confirm_category_b = False means auto-confirm ON (allowed)
            # require_confirm_category_b = True means user must confirm (not auto-allowed)
            return not self.automation_config.require_confirm_category_b
        elif perm == "C":
            # Category C tools: restricted_category_c = False means NOT restricted (allowed)
            # restricted_category_c = True means restricted/blocked
            return not self.automation_config.restricted_category_c
        return True

    async def execute_intent(self, user_intent: str) -> Dict[str, Any]:
        """Execute a user intent through the permission-aware async dispatcher."""
        steps = self.task_planner.plan(user_intent)
        self.tool_dispatcher.call_count = 0
        results = []
        for step in steps:
            tool = self.tool_registry.get(step.tool_name)
            if tool is None:
                results.append({
                    "step_id": step.step_id, "description": step.description,
                    "tool": step.tool_name, "verified": False,
                    "error": f"Tool '{step.tool_name}' not found",
                    "requires_confirmation": False
                })
                break
            if not self._check_permission(tool):
                results.append({
                    "step_id": step.step_id, "description": step.description,
                    "tool": step.tool_name, "verified": False, "result": None,
                    "error": f"Permission required for category {tool.required_permission}",
                    "requires_confirmation": True
                })
                break
            result = await self.tool_dispatcher.execute_async(step.tool_name, step.parameters)
            step.result = result
            step.verified = isinstance(result, dict) and result.get("status") in {
                "success", "navigated", "search_completed", "completed"
            }
            results.append({
                "step_id": step.step_id, "description": step.description,
                "tool": step.tool_name, "result": result,
                "verified": step.verified,
                "error": None if step.verified else (
                    result.get("error", "Step did not complete") if isinstance(result, dict) else "Step did not complete"
                ),
                "requires_confirmation": False
            })
            if not step.verified:
                break
        return {"plan": self.task_planner.get_plan_summary(), "steps": results}

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
