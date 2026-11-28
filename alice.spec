# ALICE PyInstaller spec file
# Run with: pyinstaller alice.spec

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Bundle the ONNX runtimes and phonemizer resources required by Kokoro.
extra_datas, extra_binaries, extra_hiddenimports = [], [], []
for package in ("kokoro_onnx", "onnxruntime", "phonemizer", "espeakng_loader"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    extra_datas += package_datas
    extra_binaries += package_binaries
    extra_hiddenimports += package_hiddenimports

vad_model = Path("build-assets/voice_models/silero_vad.onnx")
vad_datas = [(str(vad_model), "voice_models")] if vad_model.is_file() else []

a = Analysis(
    ['alice/main.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=[
        ('alice', 'alice'),
        ('README.md', '.'),
        ('requirements.txt', '.'),
    ] + extra_datas + vad_datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'faster_whisper',
        'kokoro_onnx',
        'onnxruntime',
        'phonemizer.backend.espeak.wrapper',
        'espeakng_loader',
        'piper_tts',
        'openwakeword',
        'sounddevice',
        'numpy',
        'psutil',
        'pywinauto',
        'wmi',
        'pythoncom',  # Required for WMI COM interface in background threads
        'win32api',
        'win32con',
        'win32gui',
        'playwright',
        'rich',
        'click',
        'aiohttp',
        'requests',
        'tqdm',
    ] + extra_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ALICE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# Optional: Create an installer
# from PyInstaller.utils.win32 import versioninfo
# version_file = versioninfo.FixedFileInfo(...)
# exe.version = version_file