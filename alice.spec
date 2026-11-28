# ALICE PyInstaller spec file
# Run with: pyinstaller alice.spec

block_cipher = None

a = Analysis(
    ['alice/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('alice', 'alice'),
        ('README.md', '.'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'faster_whisper',
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
    ],
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