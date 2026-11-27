#!/usr/bin/env python3
import sys
sys.path.insert(0, r'D:\alicegit')
from alice.tools.tools import create_default_tools

registry = create_default_tools()
print('Type:', type(registry))
print('Has .tools:', hasattr(registry, 'tools'))
print('.tools type:', type(registry.tools))
print('.tools items count:', len(registry.tools.items()) if registry.tools else 0)
print('.list_tools() count:', len(registry.list_tools()) if registry.list_tools() else 0)
print()
# Check if registry has .items()
try:
    items = registry.items()
    print('.items() works:', items)
except AttributeError as e:
    print('.items() error:', e)

# Check if registry.tools has .items()
try:
    items = registry.tools.items()
    print('.tools.items() works:', len(items), 'items')
except AttributeError as e:
    print('.tools.items() error:', e)