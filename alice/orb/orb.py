#!/usr/bin/env python3
"""
Floating Orb for ALICE.
A draggable, always-on-top UI widget with multiple states.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Orb:
    """Floating Orb UI widget for ALICE."""

    def __init__(self, config: Any, event_bus: Any = None):
        self.config = config
        self.event_bus = event_bus
        self.state: str = "idle"  # idle, listening, thinking, speaking, executing, waiting, error
        self.is_visible: bool = True
        self.position_x: int = 100
        self.position_y: int = 100
        self.size: int = 80
        self.opacity: float = 0.9
        self.is_draggable: bool = True
        self.is_always_on_top: bool = True
        self.current_text: str = ""
        self.waveform_visible: bool = False
        self.task_progress: float = 0.0

        # Subscribe to OMEN key events if event_bus provided
        if self.event_bus:
            self.event_bus.subscribe("OMEN_KEY_PRESSED", self._on_omen_key_pressed)
            logger.info("Orb subscribed to OMEN_KEY_PRESSED events")

    def _on_omen_key_pressed(self, event_data: Dict[str, Any]) -> None:
        """Handle OMEN key press - activate listening state."""
        logger.info(f"Orb received OMEN key event: {event_data}")
        self.update_state("listening")
        self.show_waveform()

    def update_state(self, new_state: str) -> None:
        """Update orb state with smooth transition."""
        valid_states = {"idle", "listening", "thinking", "speaking", "executing", "waiting", "error"}
        if new_state not in valid_states:
            logger.warning(f"Invalid state: {new_state}. Keeping current state.")
            return

        # In production, this would trigger animation
        self.state = new_state
        logger.info(f"Orb state: {new_state}")

    def set_position(self, x: int, y: int) -> None:
        """Set orb position."""
        self.position_x = x
        self.position_y = y

    def set_size(self, size: int) -> None:
        """Set orb size."""
        self.size = size

    def set_opacity(self, opacity: float) -> None:
        """Set orb opacity."""
        self.opacity = opacity

    def update_text(self, text: str) -> None:
        """Update orb display text."""
        self.current_text = text[:20]  # Truncate for display

    def show_waveform(self) -> None:
        """Show listening waveform."""
        self.waveform_visible = True

    def hide_waveform(self) -> None:
        """Hide listening waveform."""
        self.waveform_visible = False

    def set_task_progress(self, progress: float) -> None:
        """Set task progress (0.0 to 1.0)."""
        self.task_progress = max(0.0, min(1.0, progress))

    def get_status(self) -> Dict[str, Any]:
        """Get orb status."""
        return {
            "state": self.state,
            "visible": self.is_visible,
            "position": {"x": self.position_x, "y": self.position_y},
            "size": self.size,
            "opacity": self.opacity,
            "current_text": self.current_text,
            "waveform_visible": self.waveform_visible,
            "task_progress": self.task_progress,
        }

    def toggle_visibility(self) -> None:
        """Toggle orb visibility."""
        self.is_visible = not self.is_visible

    def click(self) -> None:
        """Handle orb click - typically opens dashboard or activates listening."""
        logger.info("Orb clicked")


if __name__ == "__main__":
    # Simple test
    from alice.core.config import Config
    orb = Orb(Config.load())
    print(f"Orb initial state: {orb.get_status()['state']}")
    orb.update_state("listening")
    print(f"Orb updated state: {orb.get_status()['state']}")
    orb.click()
    print(f"Orb status after click: {orb.get_status()['state']}")