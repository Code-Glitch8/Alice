#!/usr/bin/env python3
"""Main ALICE application composition root."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from alice.ai.lmstudio_adapter import LMStudioAdapter
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
        """Chat with tool calling support.

        Uses native tool calling when tools are provided to LM Studio.
        Falls back to parsing AI response if tool calls are returned as text/JSON.
        Integrates the task planner for compound commands.
        Implements an iterative tool execution loop that continues until the model
        produces a final response (not just tool calls).
        """
        if not self.initialized and not await self.initialize():
            raise RuntimeError(self.ai_adapter.last_error or "LM Studio is unavailable")

        # Prepare messages with system prompt
        messages = [{"role": "system", "content": self.system_prompt}] + history

        # Get tools for API if not provided
        if tools is None:
            tools = self.get_tools_for_api()

        # Track execution rounds to prevent infinite loops
        max_rounds = getattr(self.config, 'automation', None)
        max_rounds = getattr(max_rounds, 'max_tool_calls', 5) if max_rounds else 5
        round_count = 0

        # Store tool definitions to persist across rounds
        tool_definitions = tools

        while round_count < max_rounds:
            round_count += 1
            self.current_tool_call_count = 0  # Reset per round

            # Get response from LLM with native tool calling support
            response = await self.runtime.chat(messages, tools=tool_definitions)

            # Parse response - this now handles ALL formats including XML in content
            parsed_response = self._parse_ai_response(response)

            # Extract tool calls and content from the parsed response
            native_tool_calls = []
            content = ""

            if isinstance(parsed_response, dict):
                # Check for tool calls from native format
                if "tool_calls" in parsed_response:
                    native_tool_calls = parsed_response["tool_calls"]
                content = parsed_response.get("content") or ""
            elif isinstance(parsed_response, str):
                # Response was raw text - check for embedded XML calls
                if "<function" in parsed_response:
                    native_tool_calls = self._parse_xml_tool_calls(parsed_response)
                    # Remove XML markup from content
                    content = self._remove_xml_markup(parsed_response)
                else:
                    content = parsed_response

            # If parsed_response was None or empty, use raw response
            if not content:
                content = self._remove_xml_markup(response) if "<function" in response else response

            # Build combined tool calls list
            all_tool_calls = []
            processed_ids = set()

            # Add XML tool calls first (they have generated IDs)
            for tc in native_tool_calls:
                tc_id = tc.get("id", f"xml_{len(all_tool_calls)}")
                if tc_id not in processed_ids:
                    all_tool_calls.append(tc)
                    processed_ids.add(tc_id)

            if all_tool_calls:
                # Detect if this is a compound command that should use the planner
                if self._is_compound_command(content, all_tool_calls):
                    # Use planner for compound commands
                    return await self._execute_planned_tasks(history, content, all_tool_calls)

                # Execute tool calls and get result
                result = await self._execute_tool_calls(all_tool_calls, messages, content)

                # Build messages for next iteration
                assistant_msg = {"role": "assistant", "content": content}
                if all_tool_calls:
                    assistant_msg["tool_calls"] = all_tool_calls
                messages.append(assistant_msg)

                if isinstance(result, list):
                    messages.extend(result)
                elif result:
                    messages.append({"role": "assistant", "content": str(result)})

                # Check if we got a string result (means final response)
                if isinstance(result, str):
                    return result

                # Continue loop for next iteration
            else:
                # No tool calls found - this is our final response
                # Content should be clean (no XML markup)
                return content if content else "Task completed."

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
        """Execute compound commands using the task planner."""
        # Build a combined user message from history
        user_messages = [h for h in history if h.get("role") == "user"]
        latest_user = user_messages[-1]["content"] if user_messages else content

        # Plan the task
        steps = self.task_planner.plan(latest_user)

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
                    # Continue with unconfirmed steps for now, or return early
                    # For now, we'll skip unconfirmed tool calls
                    continue

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

        # Build response for final LLM call
        plan_summary = self.task_planner.get_plan_summary()
        results_summary = "\n".join(
            f"- Step {r['step_id']}: {r['description']} - {r['result'] if isinstance(r['result'], dict) else r['result']}"
            for r in results
        )

        # Add results to history and get final response
        messages = [{"role": "system", "content": self.system_prompt}] + history + [
            {"role": "assistant", "content": f"Executed plan: {plan_summary}\nResults:\n{results_summary}"}
        ]

        final_response = await self.runtime.chat(messages)
        return final_response

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
                        "content": json.dumps({
                            "status": "error",
                            "error": f"Permission denied for tool {tool_name} (category {tool.required_permission})"
                        })
                    })
                    continue

            # Execute tool through dispatcher (handles async tools properly)
            if tool:
                result = await self.tool_dispatcher.execute_async(tool_name, arguments)
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
