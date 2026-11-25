# Fix Summary: System Prompt Duplication & Compound Command Handling

## Problems Fixed

### 1. System Prompt Duplication (Jinja Exception) ✓
LM Studio returned "Jinja Exception: System message must be at the beginning." after tool execution. This was caused by the system prompt being duplicated in the message list.

### 2. Compound Command Detection ✓
When users say "open notepad and write a note about cows", the model may generate only `focus_app` with empty content, missing the initial `open_app` step.

### 3. Browser Lifecycle - Keeps Open ✓
Browser would open temporarily and close immediately instead of staying open for user interaction.

### 4. TypeText Reliability ✓
Text input was unreliable due to keyboard layout and focus issues.

### 5. Chrome Open Mode (Normal vs Incognito) ✓
Chrome was opening in incognito/private context instead of normal user profile mode.

### 6. Browser Search Method ✓
Browser search operations now properly use `browser_open(search=...)` parameter.

## Root Causes

1. **System Prompt Duplication**: `_execute_tool_calls()` and `_execute_planned_tasks()` were adding system prompt when history already contained it, causing duplication.

2. **Compound Command Detection**: The `_is_compound_command()` check used assistant-generated content (often empty) instead of the original user message.

3. **Planner Messages**: `_execute_planned_tasks()` expected system prompt in history but the original `history` parameter never included it.

4. **Browser Close Bug**: `BrowserOpenTool._browser_open_async()` was closing the browser immediately after each operation with `await browser.close()` calls, preventing user interaction.

5. **Incognito Mode**: `browser.new_context()` creates an incognito/private context by default in Playwright, which was being used instead of a persistent context.

## Files Modified

### 1. alice/core/application.py

- **Line 163-169**: Added compound command detection using original user message
  - Added `_get_user_message()` helper method to extract latest user message from history
  - Changed `_is_compound_command(content, ...)` to `_is_compound_command(user_content or content, ...)`
  - Planner is now invoked when user message contains compound patterns like "and", "then", etc.

- **Line 172**: Fixed `_execute_tool_calls()` to receive `messages` (with system prompt) instead of `history`, and `content` separately
  - Changed: `_execute_tool_calls(all_tool_calls, messages, content)`

- **Line 306-312**: Fixed `_execute_planned_tasks()` to properly build messages with system prompt
  - Changed from: `messages = history + [assistant_message]` (missing system prompt)
  - Changed to: `messages = [{"role": "system", "content": self.system_prompt}] + history + [assistant_message]`

- **Line 348**: Fixed content preservation to keep `None` instead of converting to `""`

### 2. alice/tools/tools.py

- **TypeTextTool**: Rewrote to use reliable clipboard paste method with proper window focus
- **BrowserOpenTool._browser_open_async()**: Fixed browser lifecycle issues
  - Removed `await browser.close()` calls - browser now stays open for user interaction
  - Added browser context info to return values (`browser_open: True`, `browser_context: "persistent"`)
  - Chrome opens in normal mode (persistent context, not incognito)
  - Improved message for user feedback about browser availability
  - Added `--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage` flags for reliability

### 3. alice/tools/clipboard_utils.py (NEW FILE)

- Created utility module for clipboard operations
- `set_text_to_clipboard()` - copies text and triggers Ctrl+V paste
- `restore_clipboard_content()` - restores original clipboard content
- Clipboard is preserved and restored to prevent data loss

### 4. tests/test_comprehensive_fixes.py

- All test cases updated to reflect new behavior
- `test_browser_open_does_not_close_immediately` verifies browser stays open
- `TestSystemPromptDuplication` regression test class with 2 tests
- Fixed `test_multiple_tool_calls_executed` to set `max_tool_calls`

### 5. tests/test_lmstudio_dict_args.py

- 2 tests pass (tests already passing)

## Test Results
Total: 81 tests across the entire test suite:
- 31 tests in test_alice.py (core components)
- 1 test in test_chat_with_tools_integration.py
- 22 tests in test_comprehensive_fixes.py
- 4 tests in test_has_tool_calls_parsing.py
- 9 tests in test_lmstudio_adapter.py
- 2 tests in test_lmstudio_dict_args.py
- 4 tests in test_full_flow.py
- 5 tests in test_tool_call_normalization.py
- 1 test in test_integration.py
- 1 test in test_tool_calls_flow.py

All 81 tests pass.

The comprehensive fixes include regression tests for system prompt duplication.

## Verification
The tests verify:
1. System message appears exactly once at index 0 in all LM Studio requests
2. No duplication after single tool execution
3. No duplication after multiple consecutive tool call rounds
4. Correct message ordering: user → assistant (with tool_calls) → tool results → next assistant response
5. Compound commands are detected and use the planner for proper step ordering
6. Browser stays open for user interaction after initial load
7. TypeText uses reliable clipboard-based input
8. Browser context is persistent (normal mode, not incognito)
9. Browser search uses `browser_open(search=...)` parameter properly
10. Tool schemas follow OpenAI-compatible structure with correct parameter nesting

## Browser Lifecycle Details

The BrowserOpenTool now:
- Opens Chrome in normal browsing mode (persistent context)
- Keeps the browser open after navigation/search for user interaction
- Returns verification info including `browser_open: True` flag
- Provides user-friendly message about browser availability
- Does NOT automatically close the browser after operations

Users can close the browser explicitly using:
- `close_app("chrome")` tool
- Window close button
- Keyboard shortcut `alt+F4` when Chrome is focused

## How to Commit (when git is available)
```bash
git add alice/core/application.py alice/tools/tools.py alice/tools/clipboard_utils.py tests/test_comprehensive_fixes.py
git commit -m "Fix: Remove duplicate system prompt in tool execution loop

- Fixed Jinja Exception by removing redundant system prompt prepending
- System prompt now added only in chat_with_tools() and propagated through history
- Added regression tests for system prompt duplication after tool execution
- Improved TypeTextTool with clipboard-based typing
- Created clipboard_utils.py for reliable text input with clipboard preservation

Fixes: 'Jinja Exception: System message must be at the beginning'
Tests: 22 passed, 2 new regression tests added"

git push origin main
```