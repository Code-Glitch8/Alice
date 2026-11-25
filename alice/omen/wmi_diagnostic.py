#!/usr/bin/env python3
"""
Simplified WMI Diagnostic for OMEN Button on HP Victus 15.
Focuses on HP-specific WMI providers and common hotkey event patterns.
"""

import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_admin():
    """Check if running as administrator."""
    import ctypes
    return ctypes.windll.shell32.IsUserAnAdmin()


def find_hp_wmi_namespaces():
    """Find HP-related WMI namespaces."""
    try:
        import wmi
        c = wmi.WMI()
        namespaces = c.ExecQuery("SELECT Name FROM __NAMESPACE WHERE Name LIKE '%hp%' OR Name LIKE '%HP%'")
        return [ns.Name for ns in namespaces]
    except Exception as e:
        logger.error(f"Error finding HP namespaces: {e}")
        return []


def find_hp_wmi_classes(namespace="root\\wmi"):
    """Find HP-related WMI classes in a namespace."""
    try:
        import wmi
        c = wmi.WMI(namespace=namespace)
        classes = c.ExecQuery("SELECT __CLASS FROM __CLASS WHERE __CLASS LIKE '%HP%' OR __CLASS LIKE '%HotKey%' OR __CLASS LIKE '%hotkey%'")
        return [cls.__CLASS for cls in classes]
    except Exception as e:
        logger.error(f"Error finding HP classes in {namespace}: {e}")
        return []


def monitor_wmi_class(namespace, class_name, duration=30):
    """Monitor a specific WMI class for events."""
    try:
        import wmi
        c = wmi.WMI(namespace=namespace)

        logger.info(f"Monitoring {namespace}\\{class_name} for {duration} seconds...")

        # Create event watcher
        query = f"SELECT * FROM {class_name}"
        watcher = c.ExecNotificationQuery(query)

        start_time = time.time()
        events_found = 0

        while (time.time() - start_time) < duration:
            try:
                event = watcher.NextEvent(1000)  # 1 second timeout
                if event:
                    events_found += 1
                    logger.info(f"  Event #{events_found}:")
                    # Print all properties
                    for prop in dir(event):
                        if not prop.startswith('_'):
                            try:
                                val = getattr(event, prop)
                                if not callable(val):
                                    logger.info(f"    {prop}: {val}")
                            except:
                                pass
                    logger.info("")
            except wmi.x_wmi_timed_out:
                pass  # Normal timeout
            except Exception as e:
                logger.debug(f"Monitor error: {e}")
                break

        logger.info(f"Monitoring complete. Events detected: {events_found}")
        return events_found > 0

    except Exception as e:
        logger.error(f"Failed to monitor {namespace}\\{class_name}: {e}")
        return False


def try_known_hp_classes():
    """Try known HP WMI classes for hotkey events."""
    known_classes = [
        ("root\\wmi", "HP_HotKey_Event"),
        ("root\\wmi", "WmiMonitorBrightnessMethods"),
        ("root\\wmi", "HP_WMI"),
        ("root\\hpq", "HP_HotKey"),
        ("root\\hpq", "HP_WMIEvents"),
        ("root\\cimv2", "Win32_HotKey"),
        ("root\\cimv2", "HP_HotKey"),
    ]

    logger.info("=" * 60)
    logger.info("Testing known HP WMI classes for OMEN button")
    logger.info("=" * 60)

    for ns, cls in known_classes:
        logger.info(f"\nTrying: {ns}\\{cls}")
        monitor_wmi_class(ns, cls, duration=10)


def monitor_all_wmi_events(duration=60):
    """Monitor all events in root\\wmi namespace (broad monitoring)."""
    try:
        import wmi
        c = wmi.WMI(namespace=r"root\wmi")

        logger.info(f"Broad monitoring of root\\wmi for {duration} seconds...")
        logger.info("Press the OMEN button now!")
        logger.info("")

        # This monitors ALL instance creation events in root\wmi
        query = "SELECT * FROM __InstanceCreationEvent"
        watcher = c.ExecNotificationQuery(query)

        start_time = time.time()
        events_found = 0

        while (time.time() - start_time) < duration:
            try:
                event = watcher.NextEvent(1000)
                if event:
                    events_found += 1
                    logger.info(f"  Event #{events_found}:")
                    target = getattr(event, 'TargetInstance', None)
                    if target:
                        for prop in dir(target):
                            if not prop.startswith('_'):
                                try:
                                    val = getattr(target, prop)
                                    if not callable(val):
                                        logger.info(f"    {prop}: {val}")
                                except:
                                    pass
                    logger.info("")
            except wmi.x_wmi_timed_out:
                pass
            except Exception as e:
                logger.debug(f"Broad monitor error: {e}")
                break

        logger.info(f"Broad monitoring complete. Events detected: {events_found}")

    except Exception as e:
        logger.error(f"Broad monitoring failed: {e}")


def check_hp_hotkey_driver():
    """Check if HP Hotkey Support driver is installed."""
    try:
        import wmi
        c = wmi.WMI()

        # Check for HP Hotkey related services/drivers
        services = c.ExecQuery("SELECT * FROM Win32_Service WHERE Name LIKE '%hp%' OR Name LIKE '%HP%' OR Name LIKE '%hotkey%' OR Name LIKE '%Hotkey%'")

        logger.info("HP-related services:")
        for svc in services:
            logger.info(f"  {svc.Name}: {svc.State} ({svc.StartMode})")

        # Check for HP WMI providers
        providers = c.ExecQuery("SELECT * FROM Win32_WMISetting")
        logger.info("WMI Settings:")
        for p in providers:
            logger.info(f"  {p}")

    except Exception as e:
        logger.error(f"Driver check failed: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OMEN Button WMI Diagnostic")
    parser.add_argument("--duration", type=int, default=60, help="Monitor duration (seconds)")
    parser.add_argument("--mode", choices=["known", "broad", "drivers", "all"], default="all",
                        help="Diagnostic mode")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("ALICE OMEN Button WMI Diagnostic")
    logger.info("Target: HP Victus 15")
    logger.info("=" * 60)

    if not check_admin():
        logger.warning("NOT RUNNING AS ADMINISTRATOR")
        logger.warning("Some WMI queries may fail or return limited results")
        logger.warning("Run as Administrator for complete results")
        logger.info("")

    if args.mode in ("drivers", "all"):
        logger.info("\n--- Checking HP Hotkey Drivers/Services ---")
        check_hp_hotkey_driver()

    if args.mode in ("known", "all"):
        logger.info("\n--- Testing Known HP WMI Classes ---")
        try_known_hp_classes()

    if args.mode in ("broad", "all"):
        logger.info("\n--- Broad WMI Event Monitoring ---")
        logger.info("PRESS THE OMEN BUTTON DURING THIS TEST")
        monitor_all_wmi_events(args.duration)

    logger.info("\n" + "=" * 60)
    logger.info("DIAGNOSTIC COMPLETE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("If you found EventID/EventData values for the OMEN button,")
    logger.info("update alice/omen/hotkey_service.py:")
    logger.info("  omen_candidate = (event_id == YOUR_EVENT_ID and event_data == YOUR_EVENT_DATA)")
    logger.info("")


if __name__ == "__main__":
    main()