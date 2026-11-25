"""Clipboard utility functions for reliable text input."""

import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def set_text_to_clipboard(text: str, target_window: Optional[str] = None) -> Dict[str, Any]:
    """Set text to clipboard and paste it into the target window.

    This is more reliable than pyautogui.typewrite() which can fail
    due to keyboard layout issues, focus problems, or rate limiting.

    Args:
        text: The text to type
        target_window: Optional window name to focus first

    Returns:
        Dict with status and verification info
    """
    try:
        import pyperclip
        import pyautogui
    except ImportError:
        logger.warning("pyperclip or pyautogui not available, clipboard method not possible")
        return {"status": "error", "error": "Missing required library (pyperclip or pyautogui)"}

    try:
        # Clear any previous clipboard content indicator
        pyperclip.copy("")
        time.sleep(0.1)

        # Set the actual text
        pyperclip.copy(text)
        time.sleep(0.1)  # Small delay to ensure clipboard is updated

        # Focus target window if specified
        if target_window:
            try:
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(target_window)
                if windows:
                    windows[0].activate()
                    time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Could not auto-focus window '{target_window}': {e}")

        # Press Ctrl+V to paste
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.2)  # Give time for paste to complete

        # Clear clipboard to avoid leaving sensitive text
        pyperclip.copy("")

        return {
            "status": "success",
            "action": "clipboard_paste",
            "text_length": len(text),
            "target_window": target_window,
            "verification": {
                "success": True,
                "method": "clipboard_paste"
            }
        }
    except Exception as e:
        logger.error(f"Clipboard paste failed: {e}")
        return {"status": "error", "error": str(e)}


def get_clipboard_text() -> str:
    """Get text from clipboard.

    Returns:
        Text currently in clipboard, or empty string if not text
    """
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return ""


def clear_clipboard() -> bool:
    """Clear the clipboard.

    Returns:
        True if successful, False otherwise
    """
    try:
        import pyperclip
        pyperclip.copy("")
        return True
    except Exception:
        return False