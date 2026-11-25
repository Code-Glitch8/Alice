#!/usr/bin/env python3
"""
OMEN Button Diagnostic Tool for HP Victus 15.
Monitors WMI events to detect the OMEN button hardware event codes.
Run this on the actual HP Victus 15 to find the correct EventID/EventData.
"""

import logging
import time
import sys
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class OMENDiagnosticMonitor:
    """WMI-based hardware event monitor for OMEN button detection."""

    def __init__(self):
        self.running = False
        self.events_logged = []
        self.lock = threading.Lock()

    def start_monitoring(self, duration_seconds: int = 60) -> None:
        """Start monitoring WMI events for the specified duration."""
        try:
            import wmi
        except ImportError:
            logger.error("pywin32/wmi not installed. Run: pip install pywin32 wmi")
            return

        logger.info(f"Starting OMEN button diagnostic monitoring for {duration_seconds} seconds...")
        logger.info("Press the OMEN button on your HP Victus 15 during this time.")
        logger.info("")

        self.running = True
        start_time = time.time()

        # Method 1: Try to monitor HP-specific WMI events
        try:
            # HP WMI provider namespace - common for HP hotkeys
            c = wmi.WMI(namespace=r"root\wmi")

            # Try to watch for HP Hotkey events (EventID 29 is common)
            watcher = c.ExecNotificationQuery(
                "SELECT * FROM HP_HotKey_Event"
            )

            logger.info("Monitoring HP_HotKey_Event WMI class...")

            while self.running and (time.time() - start_time) < duration_seconds:
                try:
                    event = watcher.NextEvent(1000)  # 1 second timeout
                    if event:
                        self._log_event("HP_HotKey_Event", event)
                except wmi.x_wmi_timed_out:
                    pass  # Timeout, continue loop
                except Exception as e:
                    logger.debug(f"WMI query error: {e}")
                    break

        except Exception as e:
            logger.warning(f"Could not monitor HP_HotKey_Event: {e}")

        # Method 2: Try generic WMI event monitoring
        try:
            c = wmi.WMI(namespace=r"root\wmi")
            # Monitor all events in root\wmi namespace
            watcher = c.ExecNotificationQuery(
                "SELECT * FROM __InstanceCreationEvent WHERE TargetInstance ISA 'MSAcpi_ThermalZoneTemperature'"
            )

            while self.running and (time.time() - start_time) < duration_seconds:
                try:
                    event = watcher.NextEvent(1000)
                    if event:
                        self._log_event("Generic_WMI", event)
                except wmi.x_wmi_timed_out:
                    pass
                except Exception as e:
                    logger.debug(f"Generic WMI error: {e}")
                    break
        except Exception as e:
            logger.warning(f"Generic WMI monitoring failed: {e}")

        # Method 3: Try Win32_Keyboard events
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            wmi_service = win32com.client.GetObject("winmgmts:\\\\.\\root\\cimv2")

            # Monitor keyboard events
            keyboard_query = "SELECT * FROM __InstanceOperationEvent WHERE TargetInstance ISA 'Win32_Keyboard'"

            sink = Win32KeyboardEventSink(self)
            connection_point = wmi_service.ExecNotificationQueryAsync(sink, keyboard_query)

            while self.running and (time.time() - start_time) < duration_seconds:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.1)

        except Exception as e:
            logger.warning(f"Win32_Keyboard monitoring failed: {e}")

        self.running = False
        self._print_summary()

    def _log_event(self, source: str, event: Any) -> None:
        """Log a detected event."""
        with self.lock:
            event_data = {
                "source": source,
                "timestamp": time.time(),
                "event_type": type(event).__name__,
            }

            # Extract useful attributes
            if hasattr(event, 'EventID'):
                event_data["EventID"] = event.EventID
            if hasattr(event, 'EventData'):
                event_data["EventData"] = event.EventData
            if hasattr(event, 'KeyCode'):
                event_data["KeyCode"] = event.KeyCode
            if hasattr(event, 'HotKeyCode'):
                event_data["HotKeyCode"] = event.HotKeyCode

            # Get all attributes
            for attr in dir(event):
                if not attr.startswith('_') and attr not in event_data:
                    try:
                        value = getattr(event, attr)
                        if not callable(value):
                            event_data[attr] = value
                    except:
                        pass

            self.events_logged.append(event_data)

            # Print immediately
            logger.info(f"EVENT DETECTED [{source}]:")
            for k, v in event_data.items():
                logger.info(f"  {k}: {v}")
            logger.info("")

    def _print_summary(self) -> None:
        """Print summary of all detected events."""
        logger.info("=" * 60)
        logger.info("OMEN BUTTON DIAGNOSTIC SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total events detected: {len(self.events_logged)}")
        logger.info("")

        if self.events_logged:
            # Group by EventID/EventData
            event_groups = {}
            for e in self.events_logged:
                key = (e.get("EventID"), e.get("EventData"))
                if key not in event_groups:
                    event_groups[key] = []
                event_groups[key].append(e)

            logger.info("Event groups (potential OMEN button signatures):")
            for (eid, edata), events in event_groups.items():
                logger.info(f"  EventID={eid}, EventData={edata}: {len(events)} occurrence(s)")
                if len(events) > 0:
                    # Show first event details
                    first = events[0]
                    for k, v in first.items():
                        if k not in ["EventID", "EventData", "timestamp"]:
                            logger.info(f"    {k}: {v}")
        else:
            logger.info("No WMI events detected. Try:")
            logger.info("  1. Run as Administrator")
            logger.info("  2. Check HP Hotkey Support is installed")
            logger.info("  3. Try pressing OMEN button more firmly")
            logger.info("  4. Check HP documentation for your specific model")

        logger.info("")
        logger.info("If you found EventID/EventData for OMEN button,")
        logger.info("update alice/omen/hotkey_service.py with the values.")


class Win32KeyboardEventSink:
    """COM sink for Win32 keyboard events."""

    def __init__(self, monitor: OMENDiagnosticMonitor):
        self.monitor = monitor

    def Indicate(self, events):
        for event in events:
            try:
                target = event.TargetInstance
                if target:
                    event_data = {
                        "source": "Win32_Keyboard",
                        "timestamp": time.time(),
                        "EventID": getattr(target, 'EventID', None),
                        "EventData": getattr(target, 'EventData', None),
                        "KeyCode": getattr(target, 'KeyCode', None),
                        "DeviceID": getattr(target, 'DeviceID', None),
                        "Name": getattr(target, 'Name', None),
                    }
                    self.monitor._log_event("Win32_Keyboard", type('Event', (), event_data)())
            except Exception as e:
                logger.debug(f"Indicate error: {e}")


def main():
    """Main entry point for OMEN diagnostic."""
    import argparse

    parser = argparse.ArgumentParser(description="OMEN Button Diagnostic for HP Victus 15")
    parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # Check for admin
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        logger.warning("NOT RUNNING AS ADMINISTRATOR - WMI monitoring may be limited")
        logger.warning("Run as Administrator for best results")
        logger.info("")

    logger.info("=" * 60)
    logger.info("ALICE OMEN Button Diagnostic Tool")
    logger.info("HP Victus 15 - Hardware Event Detection")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Instructions:")
    logger.info("  1. Run this script as Administrator")
    logger.info("  2. Press the OMEN button on your HP Victus 15")
    logger.info("  3. Watch for EventID/EventData output")
    logger.info("  4. Note the values for hotkey_service.py configuration")
    logger.info("")

    monitor = OMENDiagnosticMonitor()
    monitor.start_monitoring(args.duration)


if __name__ == "__main__":
    main()