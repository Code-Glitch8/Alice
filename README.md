# ALICE — Local Windows AI Assistant

ALICE is a local-first Windows assistant that can control your computer using natural language. It integrates with LM Studio for local LLM inference and provides real Windows automation capabilities.

## Current Phase 2 Status (✅ Complete)

**Phase 1 - LM Studio Integration:**
- Real LM Studio server connectivity through `http://127.0.0.1:1234`
- Installed-model discovery through `GET /api/v1/models`
- Model loading and unloading through LM Studio's REST API
- Chat and streamed text responses through `/v1/chat/completions`
- Async runtime manager with idle unloading

**Phase 2 - Windows Automation & Tool System:**
- ✅ Real Windows application control (open, close, focus apps via aliases, PATH, registry)
- ✅ Real keyboard/mouse automation (pyautogui, pywinauto)
- ✅ File operations (search, create, rename, copy, move, extract ZIP)
- ✅ Browser automation with Playwright (open, search, extract, download, screenshot)
- ✅ ToolRegistry with 20+ registered tools returning verified results
- ✅ TaskPlanner breaking down natural language into executable steps
- ✅ LM Studio tool-calling integration (preserves tool_calls in responses)
- ✅ Natural language intent detection (chat vs commands)
- ✅ Permission system (Category A: auto, B: confirmation, C: restricted)
- ✅ Emergency stop mechanism (mouse to corner)
- ✅ Comprehensive testing infrastructure

## Requirements

- Windows 11 recommended.
- Python 3.11 or newer.
- LM Studio installed.
- Qwen 3.5 4B GGUF already downloaded in LM Studio.
- Playwright browsers: `playwright install chromium` (run once after pip install)

Install Python dependencies from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

## Start the LM Studio server

The model being downloaded does not automatically start the API server.

1. Open LM Studio.
2. Press `Ctrl + 2` to open the Developer tab.
3. Find the local server status control and turn **Start server** on.
4. Keep the address bound to `127.0.0.1` / localhost and use port `1234` unless you deliberately changed it.
5. Leave the model unloaded if you want ALICE to load it on demand.

LM Studio's official docs also describe starting the server with `lms server start`. If the `lms` command is installed and on PATH, ALICE can attempt to start the server automatically. Otherwise, start it from the Developer tab as above.

## Configure the model

The default model selector is `qwen3.5-4b`. ALICE queries LM Studio for installed model keys and tries to match that label. LM Studio's model key is authoritative and may differ from the display name.

If automatic selection is ambiguous, create `D:\Alice\config\config.json` (or `%ALICE_HOME%\config\config.json`) and set `ai.model_name` to the exact `key` returned by LM Studio's model list endpoint.

Example:

```json
{
  "ai": {
    "runtime": "lmstudio",
    "model_name": "qwen3.5-4b",
    "base_url": "http://127.0.0.1:1234",
    "auto_start_server": true,
    "startup_timeout": 30,
    "request_timeout": 180,
    "context_length": 4096,
    "idle_timeout": 300,
    "auto_load": false,
    "temperature": 0.7,
    "max_tokens": 1024
  },
  "automation": {
    "auto_confirm_category_a": true,
    "require_confirm_category_b": true,
    "restricted_category_c": true,
    "emergency_stop_enabled": true,
    "search_all_drives": true,
    "allow_read_files": true,
    "allow_create_files_folders": true,
    "allow_edit_files": true,
    "allow_move_files": true,
    "allow_app_control": true,
    "allow_delete_files": true,
    "require_confirmation_for_destructive": true,
    "allowed_locations": [
      "C:\\Users\\USERNAME\\Desktop",
      "C:\\Users\\USERNAME\\Documents",
      "C:\\Users\\USERNAME\\Downloads"
    ]
  }
}
```

## Computer Access Manager

Open the ALICE dashboard Settings tab to configure computer access. The requested defaults enable all of these permissions:

- Search all mounted drives (Windows drive letters discovered at runtime).
- Read accessible UTF-8 text files (32 KiB per-file limit).
- Create files and folders.
- Edit existing files.
- Move and organize files and folders.
- Control installed applications and windows.
- Delete files and folders.

The settings are saved in the local ALICE config file under the `automation` section. Existing config files inherit the new defaults when loaded.

**Mandatory safety enforcement:** ALICE always asks for explicit approval before overwriting an existing file, moving a file/folder, or deleting a file/folder. The prompt includes the exact target; folder deletion also reports the number of contained items. The model cannot approve its own action by passing a tool argument. Drive roots and critical Windows installation folders are protected from destructive operations. These confirmation rules cannot be disabled in the dashboard.

ALICE does not request Administrator elevation or bypass Windows permissions. It can access only locations the signed-in Windows account can access. Drive search skips operating-system and application-installation trees to avoid spending time crawling Windows and Program Files; inaccessible folders are skipped. If **Search all mounted drives** is turned off, search is limited to configured allowed locations and the ALICE working directory.

New file tools: `read_file(path)` and `move_file(src, dst)`. File reads are text-only and bounded; binary files are not loaded into the model context.

## Available Tools

**Application Control (Category A):**
- `open_app` - Open applications (notepad, chrome, calculator, etc.)
- `close_app` - Close applications
- `focus_app` - Focus application window
- `list_running_apps` - List running processes

**File Operations (Category A):**
- `create_folder` - Create directories
- `search_files` - Search for files by name/extension across enabled drives
- `read_file` - Read a UTF-8 text file (32 KiB limit)
- `move_file` - Move or organize files/folders (explicit approval required)

**Browser Automation (Category A/B):**
- `browser_open` - Open browser or search web
- `browser_extract` - Extract text from web page
- `browser_download` - Download files (Category B)
- `browser_screenshot` - Take screenshots

**Keyboard/Mouse Automation (Category A):**
- `type_text` - Type text into active window
- `keyboard_shortcut` - Execute shortcuts (ctrl+c, alt+tab, win+d)
- `mouse_move` - Move mouse to coordinates
- `mouse_click` - Click mouse
- `mouse_scroll` - Scroll wheel
- `select_text` - Select text (all, word, line, paragraph)
- `copy_paste` - Copy, cut, paste
- `get_clipboard` / `set_clipboard` - Clipboard operations

**System (Category A):**
- `system_info` - Get CPU/RAM info
- `emergency_stop` - Emergency stop (moves mouse to corner)

## Verify the connection

From the repository root (the directory containing the `alice` package):

```powershell
python -m alice.cli --check-ai
```

This checks the local server and lists installed LLMs. It does not need to load the model.

## Interactive Chat with Tools

```powershell
python -m alice.cli --chat
```

ALICE will load the configured model when the first chat session starts. Type `/exit` to leave; the model is unloaded at exit.

**Try these commands:**
- "open notepad"
- "open calculator"
- "search for pdf files on desktop"
- "create folder TestFolder on desktop"
- "open browser and search for python tutorials"
- "type text hello world"
- "press ctrl+a"
- "take screenshot of https://example.com"

To choose an exact model key:

```powershell
python -m alice.cli --chat --model "YOUR_EXACT_LM_STUDIO_MODEL_KEY"
```

## Execute Single Intent

```powershell
python -m alice.cli --intent "open notepad and type hello"
```

## Notepad Test Scenario

```powershell
python -m alice.cli --intent "open notepad, type 'Hello from ALICE', save as test.txt on desktop"
```

## Tests

```powershell
python -m pytest -q
python -m compileall -q alice
```

The LM Studio adapter tests use a local fake HTTP server. They verify API request/response handling but do not prove that the actual installed Qwen model loads or performs well on a particular laptop. That final check must be run on the target Windows machine.

## Privacy and Safety

- The default endpoint is loopback-only (`127.0.0.1`).
- Do not enable LAN serving unless you have a specific reason and understand the access implications.
- Never execute arbitrary model-generated shell commands. All tool calls are validated against ALICE's registered tools and permission rules.
- Destructive file actions (overwrite, move, delete) always require explicit confirmation, independent of the general Category B setting.
- Category C actions are restricted by default.
- Emergency stop: move mouse to top-left corner (0,0) to trigger pyautogui failsafe.
- All automation stays local - no cloud dependencies.

## Windows Desktop Application

The main Windows app starts the PySide6 dashboard, not the diagnostic CLI:

```powershell
python -m alice.main
```

The dashboard connects to the local ALICE runtime on a background thread. Send messages from the Chat tab; approved tool calls are executed through the existing planner and tool registry. Destructive file operations and Category B actions display an explicit approval dialog.

### Voice controls

- Click **Start voice**, speak, then click **Stop & transcribe**. The transcript is placed in the chat and submitted to ALICE.
- The OMEN hardware key and configured fallback shortcut activate the same voice capture flow.
- Wake phrase detection is optional and can be disabled in Settings. It uses the local Faster-Whisper `tiny.en` model to recognize the configured phrase (default: `alice`). This consumes more CPU than a purpose-trained wake-word model.
- Faster-Whisper uses the `small` model by default on a fresh configuration (change it in Settings if you prefer faster/lighter recognition). Its model is cached in `%ALICE_HOME%\\voice\\models` (default `D:\\Alice\\voice\\models`); transcription then runs locally.
- Silero VAD detects speech and separates it from silence before transcription. It is enabled by default and can be toggled in Settings. If its ONNX model or runtime is unavailable, ALICE falls back to Faster-Whisper's built-in VAD.
- Kokoro is the default neural TTS engine. The Kokoro ONNX model and voice bank are downloaded on first spoken reply (roughly 300 MB total) into `%ALICE_HOME%\\voice\\models`; after that, voice generation runs locally. Select an English (US), English (UK), or Hindi voice in Settings and use **Preview selected voice** to listen.
- Piper is the fallback when a matching `.onnx` voice model and `.onnx.json` metadata file are installed in the ALICE voice-model folders. Windows SAPI via `pyttsx3` is the final compatibility fallback.
- Microphone recordings remain in memory only; ALICE does not save them as audio files.

Microphone access must be permitted in Windows Privacy settings. Disable microphone mute in ALICE Settings before recording. Wake-word monitoring opens the microphone while enabled; turn it off when you do not want continuous phrase monitoring.

### Startup and system tray

In Settings, users may opt in to **Start ALICE when I sign in** (per-user Windows Run key) and **Keep ALICE running in the system tray** when the window is closed. Both options are off unless selected. The tray menu can reopen ALICE, start voice capture, or exit the application.

### Build and download

The Windows GitHub Actions workflow runs the automated tests on Python 3.11 and 3.12, then builds the desktop GUI and creates:

- `ALICE-Windows-Installer` — `ALICE-Setup.exe` Inno Setup installer.
- `ALICE-Windows-Portable` — portable folder packaged as a ZIP.

Open the repository's **Actions** tab, select the latest successful **ALICE Windows Desktop Build** run, and download the corresponding artifact. The installer creates a Start Menu shortcut and supports normal uninstalling.

The CI build verifies the Python modules, automated tests, PyInstaller output, installer output, and artifact upload. It does not prove microphone hardware, OMEN-key events, a real LM Studio model, or live desktop automation work on every target computer; those require a first-run check on the Windows laptop.

### CLI diagnostics remain available

For diagnostics or terminal-only chat, use:

```powershell
python -m alice.cli --check-ai
python -m alice.cli --chat
```
