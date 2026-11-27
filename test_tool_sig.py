#!/usr/bin/env python3
import sys
import inspect
sys.path.insert(0, r'D:\alicegit')
from alice.tools.tools import create_default_tools, ToolRegistry, OpenAppTool

registry = create_default_tools()

# Check OpenAppTool signature
open_app_tool = registry.tools.get('open_app')
print("open_app tool signature:")
sig = inspect.signature(open_app_tool.execute)
print(sig)
print()

# Check ListInstalledAppsTool signature
list_tool = registry.tools.get('list_installed_apps')
print("list_installed_apps tool signature:")
sig = inspect.signature(list_tool.execute)
print(sig)
print()

# Check a few more
for name in ['close_app', 'focus_app', 'create_folder', 'search_files', 'type_text', 'keyboard_shortcut',
             'mouse_move', 'mouse_click', 'mouse_scroll', 'select_text', 'copy_paste',
             'get_clipboard', 'set_clipboard', 'system_info', 'list_running_apps',
             'get_app_status', 'close_all_apps', 'get_open_apps', 'emergency_stop',
             'read_file', 'move_file', 'write_file', 'delete_file', 'delete_folder',
             'browser_open', 'browser_extract', 'browser_download', 'browser_screenshot']:
    tool = registry.tools.get(name)
    if tool:
        try:
            sig = inspect.signature(tool.execute)
            print(f"{name}: {sig}")
        except ValueError as e:
            print(f"{name}: Error - {e}")