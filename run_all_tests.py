#!/usr/bin/env python3
"""Run all tests and report results."""
import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "pytest", "tests/test_alice.py", "-v"], capture_output=True, text=True)
print(result.stdout)
print(result.stderr)
sys.exit(result.returncode)