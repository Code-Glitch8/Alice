---
name: comprehensive-fixes
description: Complete fixes for ALICE 1.0.8 tool execution and browser lifecycle issues
metadata:
  node_type: memory
  type: project
  originSessionId: 4418abed-1cd7-4912-a11f-dfa52a40cdc1
  modified: 2026-11-25T07:46:48.717Z
---

# Comprehensive Fixes Summary

All 69 tests pass. Fixes implemented for ALICE v1.0.8:

## 1. System Prompt Duplication (Jinja Exception) ✓
- Fixed by ensuring system prompt is added only in `chat_with_tools()` at message construction
- System prompt is propagated through history and not re-added in `_execute_tool_calls()` or `_execute_planned_tasks()`
- Verified with regression tests `test_system_prompt_appears_once_after_tool_execution` and `test_multiple_consecutive_tool_calls_no_system_duplication`

## 2. Compound Command Detection ✓
- Added `_get_user_message()` helper method to extract latest user message from history
- Changed `_is_compound_command(content, ...)` to `_is_compound_command(user_content or content, ...)`
- Planner now correctly detects compound commands using original user message

## 3. Browser Lifecycle - Keeps Open ✓
- Removed `await browser.close()` calls from `BrowserOpenTool._browser_open_async()`
- Browser now stays open for user interaction after initial load
- Added `browser_open: True` flag in verification and informative message

## 4. Chrome Normal Mode (Not Incognito) ✓
- Browser now uses persistent context instead of incognito context
- Users can interact with the browser as expected
- Context is properly set with normal browsing profile

## 5. Browser Search Method ✓
- `browser_open(search=...)` parameter works correctly
- Search queries properly navigate to Google search results
- Returns `search_completed` status with verification info

## 6. TypeText Reliability ✓
- Rewrote TypeTextTool to use reliable clipboard paste method with proper window focus
- Created `clipboard_utils.py` with `set_text_to_clipboard()` function
- Clipboard is preserved and restored to prevent data loss

## 7. XML Tool Call Parsing (Qwen) ✓
- Already handled in `_parse_xml_tool_calls()` method
- Parses `<function=name><parameter>value</parameter></function>` format

## 8. LM Studio Dict Args Normalization ✓
- Dict arguments from LM Studio native API are normalized to JSON strings
- Ensures consistent tool schema structure

## Files Modified
- alice/core/application.py - System prompt handling, compound command detection
- alice/tools/tools.py - Browser lifecycle, TypeText reliability
- alice/tools/clipboard_utils.py - NEW FILE for clipboard utilities
- tests/test_comprehensive_fixes.py - Test fixes and regression tests

## Test Counts
- Total: 69 tests pass
- test_comprehensive_fixes.py: 22 tests