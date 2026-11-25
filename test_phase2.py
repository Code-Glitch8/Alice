#!/usr/bin/env python3
"""Test Phase 2+ components."""
import sys
sys.path.insert(0, '.')

print('=== Phase 2+ Component Verification ===')
print()

# 1. Runtime Manager
from alice.ai.runtime_manager import RuntimeManager
from alice.core.config import Config
from alice.ai.lmstudio_adapter import LMStudioAdapter

config = Config.load()
adapter = LMStudioAdapter(config)
manager = RuntimeManager(adapter, config)
status = manager.get_status()
print(f'1. Runtime Manager: OK - status keys: {list(status.keys())}')

# 2. Wake Word Detector
from alice.voice.wake_word import WakeWordDetector

detector = WakeWordDetector(config)
dw_status = detector.get_status()
print(f'2. Wake Word Detector: OK - status: {dw_status}')

# 3. Piper TTS
from alice.voice.tts import PiperTTS

tts = PiperTTS(config)
info = tts.get_voice_info()
print(f'3. Piper TTS: OK - voice info: {info}')

# 4. File Operations
from alice.computer.file_operations import FileOperations

fo = FileOperations(config)
file_info = fo.get_file_info('alice/main.py')
print(f'4. File Operations: OK - file: {file_info.get("name", "N/A")}')

# 5. Test planner with new steps
from alice.tools.tools import create_default_tools
from alice.planner.planner import TaskPlanner

planner = TaskPlanner(create_default_tools())

test_cases = [
    'Open Chrome',
    'Find latest PDF in Downloads',
    'Create folder Physics Notes on Desktop',
    'Extract test ZIP',
    'Search Chrome for Python docs',
]

for intent in test_cases:
    steps = planner.plan(intent)
    print(f'5. Planner: "{intent}" -> {len(steps)} step(s)')

print()
print('=== All Phase 2+ components verified ===')