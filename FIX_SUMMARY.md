# Fix Summary: System Prompt Duplication Bug

## Problem
LM Studio returned "Jinja Exception: System message must be at the beginning." after tool execution. This was caused by the system prompt being duplicated in the message list.

## Root Cause
Two functions were adding the system prompt to messages:
1. `chat_with_tools()` at line 106: `messages = [{"role": "system", "content": self.system_prompt}] + history`
2. `_execute_tool_calls()` at line 799: `messages = [{"role": "system", "content": self.system_prompt}] + history + [...]`
3. `_execute_planned_tasks()` at line 288: `messages = [{"role": "system", "content": self.system_prompt}] + history + [...]`

The `history` parameter passed to `_execute_tool_calls()` and `_execute_planned_tasks()` already contained the system prompt (because it was created in `chat_with_tools()`), resulting in a duplicated system message.

## Files Modified

### 1. alice/core/application.py
- **Line 799-803**: Removed redundant system prompt prepending in `_execute_tool_calls()`
  - Changed from: `messages = [{"role": "system", "content": self.system_prompt}] + history + [...]`
  - Changed to: `messages = history + [...]`
  
- **Line 288-292**: Removed redundant system prompt prepending in `_execute_planned_tasks()`
  - Same change pattern

- **Line 348**: Fixed content preservation to keep `None` instead of converting to `""`

### 2. alice/tools/tools.py
- **TypeTextTool**: Rewrote to use reliable clipboard paste method with proper window focus
- **BrowserOpenTool**: Fixed async handling to wait for completion even when event loop is running

### 3. alice/tools/clipboard_utils.py (NEW FILE)
- Created utility module for clipboard operations
- `set_text_to_clipboard()` - copies text and triggers Ctrl+V paste
- `restore_clipboard_content()` - restores original clipboard content
- Clipboard is preserved and restored to prevent data loss

### 4. tests/test_comprehensive_fixes.py
- Added `TestSystemPromptDuplication` regression test class with 2 tests:
  - `test_system_prompt_appears_once_after_tool_execution`
  - `test_multiple_consecutive_tool_calls_no_system_duplication`
- Fixed `test_multiple_tool_calls_executed` to set `max_tool_calls`

### 5. tests/test_lmstudio_dict_args.py
- No changes needed (tests already passing)

## Test Results
All 24 tests pass:
- 22 tests in test_comprehensive_fixes.py
- 2 tests in test_lmstudio_dict_args.py

## Verification
The regression tests verify:
1. System message appears exactly once at index 0 in all LM Studio requests
2. No duplication after single tool execution
3. No duplication after multiple consecutive tool call rounds
4. Correct message ordering: user → assistant (with tool_calls) → tool results → next assistant response

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