#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')
from alice.tools.tools import create_default_tools

registry = create_default_tools()
print("Tool names:", list(registry.tools.keys())[:5])
print()

# Check a tool
open_app_tool = registry.tools.get('open_app')
print("open_app tool:", open_app_tool)
print("type:", type(open_app_tool))
print("has schema:", hasattr(open_app_tool, 'schema'))
print("dir:", [x for x in dir(open_app_tool) if not x.startswith('__')][:20])
print()

# Check another tool
list_installed = registry.tools.get('list_installed_apps')
print("list_installed_apps tool:", list_installed)
print("type:", type(list_installed))
print("has schema:", hasattr(list_installed, 'schema'))
print()

# Check Tool base class
from alice.tools.tools import Tool
print("Tool base class has schema?:", hasattr(Tool, 'schema'))
print("Tool.__init__ signature:")
import inspect
try:
    sig = inspect.signature(Tool.__init__)
    print(sig)
except:
    print("Cannot get signature")