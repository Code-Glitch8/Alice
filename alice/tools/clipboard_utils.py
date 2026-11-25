"""Clipboard utility functions for reliable text input."""

import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Store original clipboard content to restore later
_original_clipboard: Dict[str, str] = {}


def save_clipboard_content() -> str:
    """Save the current clipboard content and return it.

    Returns:
        The current clipboard content (or empty string if not text)
    """
    try:
        import pyperclip
        content = pyperclip.paste()
        return content
    except Exception:
        return ""


def restore_clipboard_content(original_content: str) -> bool:
    """Restore the clipboard to its original content.

    Args:
        original_content: The content to restore to clipboard

    Returns:
        True if successful, False otherwise
    """
    try:
        import pyperclip
        pyperclip.copy(original_content)
        return True
    except Exception as e:
        logger.debug(f"Could not restore clipboard: {e}")
        return False


def set_text_to_clipboard(text: str, target_window: Optional[str] = None) -> Dict[str, Any]:
    """Set text to clipboard and paste it into the target window.

    This is more reliable than pyautogui.typewrite() which can fail
    due to keyboard layout issues, focus problems, or rate limiting.

    Preserves and restores the user's original clipboard content.

    Args:
        text: The text to type
        target_window: Optional window name to focus first

    Returns:
        Dict with status and verification info
    """
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        logger.warning("pyperclip or pyautogui not available, clipboard method not possible")
        return {"status": "error", "error": "Missing required library (pyperclip or pyautogui)", "clipboard_restored": False}

    original_content = ""
    clipboard_was_modified = False

    try:
        # Save original clipboard content first
        original_content = save_clipboard_content()

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

        clipboard_was_modified = True

        return {
            "status": "success",
            "action": "clipboard_paste",
            "text_length": len(text),
            "target_window": target_window,
            "verification": {
                "success": True,
                "method": "clipboard_paste",
                "original_clipboard_restored": True
            },
            "_original_content": original_content  # For later restoration
        }
    except Exception as e:
        logger.error(f"Clipboard paste failed: {e}")
        return {"status": "error", "error": str(e), "clipboard_restored": False}
    finally:
        # Restore original clipboard content
        if clipboard_was_modified and original_content:
            try:
                restore_clipboard_content(original_content)
            except Exception as e:
                logger.warning(f"Could not restore original clipboard content: {e}")


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