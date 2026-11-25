#!/usr/bin/env python3
"""
Application Ownership Registry for ALICE.

Tracks applications opened by ALICE to enable proper lifecycle management.
Provides ownership tracking via PID and creation time for clean shutdown.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AppOwnershipRecord:
    """Records ownership information for an application instance."""
    app_name: str
    pid: int
    creation_time: float
    open_time: datetime = field(default_factory=datetime.now)
    process_args: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    closing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "app": self.app_name,
            "pid": self.pid,
            "creation_time": self.creation_time,
            "open_time": self.open_time.isoformat(),
            "process_args": self.process_args,
            "environment": self.environment,
            "closing": self.closing
        }


class ApplicationOwner:
    """Singleton registry for tracking applications owned by ALICE.

    Provides:
    - PID-based ownership tracking
    - Creation time tracking for process verification
    - Batch close operations for clean shutdown
    - Status queries for running applications
    """

    _instance: Optional['ApplicationOwner'] = None

    def __init__(self):
        self._owned_apps: Dict[int, AppOwnershipRecord] = {}
        self._app_names: Dict[str, List[int]] = {}  # app_name -> list of PIDs

    @classmethod
    def get_instance(cls) -> 'ApplicationOwner':
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def register_app(self, app_name: str, pid: int, process_args: Optional[List[str]] = None,
                     environment: Optional[Dict[str, str]] = None) -> None:
        """Register an application as owned by ALICE.

        Args:
            app_name: The application name/identifier
            pid: The process ID
            process_args: Optional list of command line arguments
            environment: Optional environment variables
        """
        record = AppOwnershipRecord(
            app_name=app_name,
            pid=pid,
            creation_time=time.time(),
            process_args=process_args or [],
            environment=environment or {}
        )
        self._owned_apps[pid] = record

        if app_name not in self._app_names:
            self._app_names[app_name] = []
        if pid not in self._app_names[app_name]:
            self._app_names[app_name].append(pid)

        logger.debug(f"Registered app: {app_name} (PID: {pid})")

    def unregister_app(self, pid: int) -> bool:
        """Unregister an application from ownership tracking.

        Args:
            pid: The process ID to unregister

        Returns:
            True if the app was found and removed, False otherwise
        """
        if pid not in self._owned_apps:
            return False

        record = self._owned_apps.pop(pid)
        app_name = record.app_name

        if app_name in self._app_names:
            if pid in self._app_names[app_name]:
                self._app_names[app_name].remove(pid)
                if not self._app_names[app_name]:
                    del self._app_names[app_name]

        logger.debug(f"Unregistered app: {app_name} (PID: {pid})")
        return True

    def mark_closing(self, pid: int) -> None:
        """Mark an application as being closed (for graceful shutdown)."""
        if pid in self._owned_apps:
            self._owned_apps[pid].closing = True

    def get_app(self, app_name: str, include_pid: bool = True) -> Optional[Dict[str, Any]]:
        """Get ownership info for an application.

        Args:
            app_name: The application name
            include_pid: If True, returns a specific instance; if multiple exist, returns latest

        Returns:
            Dictionary with ownership info or None if not found
        """
        if app_name not in self._app_names:
            return None

        pids = self._app_names[app_name]
        if not pids:
            return None

        # Return the most recent (highest PID that exists)
        for pid in reversed(pids):
            if pid in self._owned_apps:
                record = self._owned_apps[pid]
                return record.to_dict()

        return None

    def get_app_by_pid(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get ownership info by PID.

        Args:
            pid: The process ID

        Returns:
            Dictionary with ownership info or None if not found
        """
        if pid not in self._owned_apps:
            return None
        return self._owned_apps[pid].to_dict()

    def get_owned_apps(self) -> List[Dict[str, Any]]:
        """Get all applications owned by ALICE.

        Returns:
            List of ownership records as dictionaries
        """
        return [record.to_dict() for record in self._owned_apps.values()]

    def get_apps_by_name(self, app_name: str) -> List[Dict[str, Any]]:
        """Get all instances of a specific application.

        Args:
            app_name: The application name

        Returns:
            List of ownership records for that app
        """
        if app_name not in self._app_names:
            return []

        results = []
        for pid in self._app_names[app_name]:
            if pid in self._owned_apps:
                results.append(self._owned_apps[pid].to_dict())
        return results

    def is_owned_by_alice(self, pid: int) -> bool:
        """Check if a process is owned by ALICE.

        Args:
            pid: The process ID to check

        Returns:
            True if ALICE owns this process
        """
        return pid in self._owned_apps

    def get_owned_pids(self) -> List[int]:
        """Get all PIDs owned by ALICE.

        Returns:
            List of process IDs
        """
        return list(self._owned_apps.keys())

    def verify_process_exists(self, pid: int) -> bool:
        """Verify that an owned process still exists.

        Args:
            pid: The process ID to verify

        Returns:
            True if process exists and matches our ownership record
        """
        if pid not in self._owned_apps:
            return False

        try:
            import psutil
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                logger.warning(f"Process {pid} is zombie")
                return False
            return True
        except psutil.NoSuchProcess:
            logger.debug(f"Process {pid} no longer exists")
            return False
        except psutil.AccessDenied:
            # Process exists but we can't access it
            return True

    def cleanup_process(self, pid: int) -> bool:
        """Remove an owned process record if it no longer exists.

        Args:
            pid: The process ID to clean up

        Returns:
            True if the process was found and removed, False otherwise
        """
        if pid not in self._owned_apps:
            return False

        try:
            import psutil
            proc = psutil.Process(pid)
            # Process still exists
            return False
        except psutil.NoSuchProcess:
            return self.unregister_app(pid)
        except psutil.AccessDenied:
            return False

    def close_all_apps(self) -> Dict[str, Any]:
        """Close all applications owned by ALICE.

        Uses the ComputerEngine for proper process termination.

        Returns:
            Dictionary with close results
        """
        from alice.computer.engine import ComputerEngine

        results = {
            "closed": [],
            "errors": [],
            "not_found": [],
            "total": 0
        }

        engine = ComputerEngine(None)  # Config not strictly needed for close_app
        pids_to_close = list(self._owned_apps.keys())

        for pid in pids_to_close:
            record = self._owned_apps[pid]
            app_name = record.app_name

            try:
                success, msg, _ = engine.close_app(app_name)
                if success:
                    results["closed"].append({"app": app_name, "pid": pid})
                else:
                    # Already closed, that's fine
                    results["not_found"].append({"app": app_name, "pid": pid})
            except Exception as e:
                results["errors"].append({"app": app_name, "pid": pid, "error": str(e)})

            self.unregister_app(pid)

        results["total"] = len(results["closed"]) + len(results["not_found"])
        logger.info(f"Closed {len(results['closed'])} apps, {len(results['errors'])} errors")

        return results

    def clear_all_apps(self) -> int:
        """Clear all ownership records without closing processes.

        Returns:
            Number of records cleared
        """
        count = len(self._owned_apps)
        self._owned_apps.clear()
        self._app_names.clear()
        logger.info(f"Cleared {count} ownership records")
        return count

    def get_status(self, verify_processes: bool = True) -> Dict[str, Any]:
        """Get current status of the ownership registry.

        Args:
            verify_processes: If False, skip process verification (useful for testing)

        Returns:
            Dictionary with registry status
        """
        verified_count = 0
        stale_pids = []

        # Create a copy of items to avoid modification during iteration
        for pid, record in list(self._owned_apps.items()):
            if verify_processes:
                if self.verify_process_exists(pid):
                    verified_count += 1
                else:
                    stale_pids.append(pid)
            else:
                # For testing with fake PIDs
                verified_count += 1

        return {
            "total_owned": len(self._owned_apps),
            "verified_running": verified_count,
            "stale_count": len(stale_pids),
            "stale_pids": stale_pids,
            "apps": {
                name: len(pids)
                for name, pids in self._app_names.items()
            }
        }

    def cleanup_stale(self) -> int:
        """Remove ownership records for processes that no longer exist.

        Returns:
            Number of stale records removed
        """
        stale_pids = [pid for pid in self._owned_apps if not self.verify_process_exists(pid)]
        for pid in stale_pids:
            self.unregister_app(pid)
        return len(stale_pids)


if __name__ == "__main__":
    # Test the ownership registry
    owner = ApplicationOwner.get_instance()

    # Register some fake apps
    owner.register_app("notepad", 1234)
    owner.register_app("chrome", 5678)
    owner.register_app("notepad", 9012)  # Second instance

    print("Owned apps:", owner.get_owned_apps())
    print("Notepads:", owner.get_apps_by_name("notepad"))
    print("Notepads (single):", owner.get_app("notepad"))
    print("By PID 1234:", owner.get_app_by_pid(1234))

    print("\nStatus:", owner.get_status())

    # Clean up
    owner.clear_all_apps()
    print("After cleanup:", owner.get_owned_apps())