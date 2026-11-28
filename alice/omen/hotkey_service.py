#!/usr/bin/env python3
"""
ALICE Hotkey Service - OMEN button and hardware key detection.
Listens for Windows hardware events and triggers ALICE activation.
Supports WMI event monitoring with configurable event IDs.
Integrates with EventBus for IPC communication.
"""

import logging
from typing import Any, Dict, Optional, List, Callable
import asyncio
import threading
import time

logger = logging.getLogger(__name__)


class HotkeyService:
    """Windows hardware event listener for ALICE activation."""

    def __init__(self, config: Any, event_bus: Any = None):
        self.config = config
        self.event_bus = event_bus
        self.is_running = False
        self.event_callbacks: List[Callable] = []
        self.last_event_time = 0.0

        # OMEN button event signature - configurable via config
        # Verified on HP Victus 15: EventID=29, EventData=8613 from hpqBEvnt class
        if config and hasattr(config, 'omen'):
            self.omen_event_id = config.omen.event_id or 29
            self.omen_event_data = config.omen.event_data or 8613
            self.wmi_namespace = config.omen.wmi_namespace or "root\\wmi"
            self.debounce_ms = config.omen.debounce_ms or 1000
            self.suppress_default_launch = getattr(config.omen, 'suppress_default_launch', False)
            self.diagnostic_mode = getattr(config.omen, 'diagnostic_mode', False)
            self.fallback_shortcut = getattr(config.omen, 'fallback_shortcut', 'ctrl+alt+a')
        else:
            self.omen_event_id = 29
            self.omen_event_data = 8613
            self.wmi_namespace = "root\\wmi"
            self.debounce_ms = 1000
            self.suppress_default_launch = False
            self.diagnostic_mode = False
            self.fallback_shortcut = "ctrl+alt+a"

        # WMI monitoring thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Fallback keyboard shortcut
        self._keyboard_hook = None

    async def start(self) -> bool:
        """Start the hotkey service."""
        logger.info("Starting ALICE Hotkey Service...")
        logger.info(f"OMEN button signature: EventID={self.omen_event_id}, EventData={self.omen_event_data}")

        self.is_running = True
        self._stop_event.clear()

        # Start WMI monitoring in background thread
        self._monitor_thread = threading.Thread(target=self._wmi_monitor_loop, daemon=True)
        self._monitor_thread.start()

        # Start fallback keyboard listener
        self._start_keyboard_listener()

        logger.info("ALICE Hotkey Service started")
        return True

    async def stop(self) -> bool:
        """Stop the hotkey service."""
        self.is_running = False
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

        self._stop_keyboard_listener()

        logger.info("Stopped ALICE Hotkey Service")
        return True

    def register_callback(self, callback: Callable) -> None:
        """Register a callback for OMEN key events."""
        self.event_callbacks.append(callback)
        logger.debug("Registered hotkey event callback")

    def _process_event(self, event_id: Optional[int], event_data: Optional[int]) -> None:
        """Process a hardware event (thread-safe)."""
        current_time = time.time()

        # Debounce: ignore if same event occurred within configured time
        debounce_seconds = self.debounce_ms / 1000.0
        if current_time - self.last_event_time < debounce_seconds:
            return

        # Check for OMEN key event
        omen_candidate = (
            event_id == self.omen_event_id and event_data == self.omen_event_data
        )

        logger.info(f"Hardware event: event_id={event_id}, event_data={event_data}, omen_candidate={omen_candidate}")

        if omen_candidate and self.is_running:
            logger.info("Detected OMEN key event - triggering ALICE activation")
            # Trigger callbacks (activate ALICE)
            for callback in self.event_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            # Publish to EventBus for IPC communication
            if self.event_bus:
                try:
                    self.event_bus.publish("OMEN_KEY_PRESSED", {
                        "event_id": event_id,
                        "event_data": event_data,
                        "source": "wmi",
                        "timestamp": current_time
                    })
                    logger.debug("Published OMEN_KEY_PRESSED to EventBus")
                except Exception as e:
                    logger.error(f"EventBus publish error: {e}")

        self.last_event_time = current_time

    def _wmi_monitor_loop(self) -> None:
        """WMI event monitoring loop (runs in background thread)."""
        logger.info("WMI monitor thread started")

        if self.diagnostic_mode:
            logger.info(f"[DIAGNOSTIC] OMEN config: event_id={self.omen_event_id}, event_data={self.omen_event_data}, "
                       f"namespace={self.wmi_namespace}, debounce_ms={self.debounce_ms}, "
                       f"fallback={self.fallback_shortcut}, suppress_launch={self.suppress_default_launch}")

        try:
            import wmi
            import pythoncom

            pythoncom.CoInitialize()

            # Use the configured WMI namespace (default: root\wmi)
            ns = self.wmi_namespace

            watcher = None
            try:
                c = wmi.WMI(namespace=ns)

                # Try the verified HP Victus 15 OMEN button WMI class
                # User verified: hpqBEvnt with EventID=29, EventData=8613
                query = (
                    f"SELECT * FROM hpqBEvnt "
                    f"WHERE EventID = {self.omen_event_id} AND EventData = {self.omen_event_data}"
                )
                watcher = c.ExecNotificationQuery(query)
                logger.info(
                    f"WMI monitoring active on {ns}\\hpqBEvnt - "
                    f"OMEN key detection (EventID={self.omen_event_id}, EventData={self.omen_event_data})"
                )
            except Exception as e:
                logger.debug(f"Could not monitor {ns}\\hpqBEvnt with verified query: {e}")

                # Fallback: try generic HP_HotKey_Event (older HP models)
                fallback_queries = [
                    ("HP_HotKey_Event", f"SELECT * FROM HP_HotKey_Event"),
                    ("HP_WMI", f"SELECT * FROM HP_WMI"),
                    ("HP_HotKey", f"SELECT * FROM HP_HotKey"),
                ]

                for class_name, query in fallback_queries:
                    try:
                        c = wmi.WMI(namespace=ns)
                        watcher = c.ExecNotificationQuery(query)
                        logger.info(f"WMI monitoring active on {ns}\\{class_name} (fallback)")
                        break
                    except Exception as fe:
                        logger.debug(f"Could not monitor {ns}\\{class_name}: {fe}")
                        continue

            # Fallback: broad monitoring for any WMI event
            if watcher is None:
                try:
                    c = wmi.WMI(namespace=r"root\wmi")
                    query = "SELECT * FROM hpqBEvnt"
                    watcher = c.ExecNotificationQuery(query)
                    logger.info("WMI monitoring active (broad hpqBEvnt mode on root\\wmi)")
                except Exception as e:
                    logger.warning(f"Broad WMI monitoring failed: {e}")

            if watcher is None:
                logger.error("Could not establish any WMI monitoring - OMEN key detection disabled")
                return

            # Event loop
            while self.is_running and not self._stop_event.is_set():
                try:
                    event = watcher.NextEvent(1000)  # 1 second timeout
                    if event:
                        self._extract_and_process_event(event)
                except wmi.x_wmi_timed_out:
                    pass  # Normal timeout, continue
                except Exception as e:
                    logger.debug(f"WMI event loop error: {e}")
                    break

        except ImportError:
            logger.warning("pywin32/wmi not available - WMI monitoring disabled")
            logger.warning("Install with: pip install pywin32 wmi")
        except Exception as e:
            logger.error(f"WMI monitor thread error: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except:
                pass
            logger.info("WMI monitor thread stopped")

    def _extract_and_process_event(self, event: Any) -> None:
        """Extract event ID/data from WMI event and process."""
        event_id = None
        event_data = None

        # Try common property names
        for prop in ['EventID', 'EventId', 'event_id']:
            if hasattr(event, prop):
                try:
                    event_id = int(getattr(event, prop))
                    break
                except:
                    pass

        for prop in ['EventData', 'EventDatum', 'event_data', 'HotKeyCode', 'KeyCode']:
            if hasattr(event, prop):
                try:
                    event_data = int(getattr(event, prop))
                    break
                except:
                    pass

        # Also check TargetInstance for nested events
        target = getattr(event, 'TargetInstance', None)
        if target:
            for prop in ['EventID', 'EventId', 'event_id']:
                if hasattr(target, prop):
                    try:
                        event_id = int(getattr(target, prop))
                        break
                    except:
                        pass
            for prop in ['EventData', 'EventDatum', 'event_data', 'HotKeyCode', 'KeyCode']:
                if hasattr(target, prop):
                    try:
                        event_data = int(getattr(target, prop))
                        break
                    except:
                        pass

        if event_id is not None or event_data is not None:
            self._process_event(event_id, event_data)

    def _start_keyboard_listener(self) -> None:
        """Start fallback keyboard shortcut listener."""
        try:
            import keyboard
            # Register hotkey from config (default: ctrl+alt+a)
            keyboard.add_hotkey(self.fallback_shortcut, self._on_keyboard_hotkey)
            logger.info(f"Fallback keyboard hotkey registered: {self.fallback_shortcut}")
        except ImportError:
            logger.debug("keyboard module not available - keyboard hotkey disabled")
        except Exception as e:
            logger.warning(f"Keyboard hotkey registration failed: {e}")

    def _stop_keyboard_listener(self) -> None:
        """Stop keyboard listener."""
        try:
            import keyboard
            keyboard.unhook_all()
        except:
            pass

    def _on_keyboard_hotkey(self) -> None:
        """Handle fallback keyboard hotkey."""
        logger.info("Fallback keyboard hotkey triggered (Ctrl+Alt+A)")
        self._process_event(self.omen_event_id, self.omen_event_data)

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "is_running": self.is_running,
            "event_id": self.omen_event_id,
            "event_data": self.omen_event_data,
            "wmi_namespace": self.wmi_namespace,
            "debounce_ms": self.debounce_ms,
            "fallback_shortcut": self.fallback_shortcut,
            "suppress_default_launch": self.suppress_default_launch,
            "diagnostic_mode": self.diagnostic_mode,
            "wmi_monitoring": self._monitor_thread is not None and self._monitor_thread.is_alive(),
            "callbacks_registered": len(self.event_callbacks),
        }

    async def watch_events(self) -> None:
        """Main event loop - kept for compatibility."""
        logger.debug("Hotkey event watch loop running (handled by background thread)")


if __name__ == "__main__":
    from alice.core.config import Config
    import asyncio

    config = Config.load()
    service = HotkeyService(config)

    async def test():
        await service.start()
        print(f"Hotkey service running: {service.get_status()['is_running']}")
        print("Press Ctrl+Alt+A to test fallback hotkey, or OMEN button for hardware event")
        print("Press Ctrl+C to stop")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await service.stop()

    asyncio.run(test())