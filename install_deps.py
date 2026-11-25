#!/usr/bin/env python3
import subprocess
import sys

packages = ['psutil', 'pyautogui', 'pywinauto']

for pkg in packages:
    try:
        __import__(pkg)
        print(f"{pkg} already installed")
    except ImportError:
        print(f"Installing {pkg}...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
        print(f"{pkg} installed successfully")

print("All dependencies ready!")