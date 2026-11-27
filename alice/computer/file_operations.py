#!/usr/bin/env python3
"""
File Operations Engine for ALICE.
Provides search, create, move, copy, rename, and extract operations.
"""

import logging
import asyncio
import shutil
import zipfile
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from alice.core.access_manager import ComputerAccessManager, is_within

logger = logging.getLogger(__name__)


class FileOperations:
    """Local file operations engine for ALICE."""

    def __init__(self, config: Any):
        self.config = config
        self.allowed_locations: List[str] = config.automation.allowed_locations

    # Search operations
    def search_files(self, query: str, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search allowed folders for matching files and directories.

        A supplied folder may be any descendant of an allowed root. Directory
        names (including hidden folders such as .pytest_cache) are searchable.
        """
        query = str(query or "").strip()
        if not query:
            return []
        query_lower = query.casefold()
        results: List[Dict[str, Any]] = []

        def is_within(path: Path, root: Path) -> bool:
            try:
                path.resolve().relative_to(root.resolve())
                return True
            except (ValueError, OSError):
                return False

        # Roots are discovered from the current configuration. With
        # search_all_drives enabled this includes every mounted drive that the
        # current Windows account can access, plus the current project folder.
        allowed_roots = ComputerAccessManager(self.config).roots()

        if folder:
            requested = Path(os.path.expandvars(str(folder))).expanduser()
            try:
                requested = requested.resolve()
            except (OSError, RuntimeError):
                return []
            if not any(is_within(requested, root) for root in allowed_roots):
                logger.warning("Search folder %s is outside allowed locations", requested)
                return []
            search_roots = [requested]
        else:
            search_roots = allowed_roots

        # Dot-prefixed folder names are not file extensions. Extension matching
        # is only enabled for conventional short suffixes such as .pdf or .txt.
        extension_query = (
            query_lower.startswith(".")
            and len(query_lower) > 1
            and len(query_lower) <= 12
            and query_lower[1:].replace("_", "").replace("-", "").isalnum()
        )

        for root in search_roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                for current, dirs, files in os.walk(root, onerror=lambda exc: logger.debug("Search access error: %s", exc)):
                    # Avoid noisy/system trees while retaining hidden project folders.
                    dirs[:] = [d for d in dirs if d.casefold() not in {
                        "node_modules", ".git", "__pycache__", "windows",
                        "system volume information", "$recycle.bin", "recovery",
                        "program files", "program files (x86)", "programdata",
                        "perfLogs".casefold()
                    }]
                    current_path = Path(current)
                    for dirname in dirs:
                        if query_lower in dirname.casefold():
                            p = current_path / dirname
                            results.append({
                                "name": dirname, "path": str(p), "type": "directory",
                                "size": 0, "modified": p.stat().st_mtime
                            })
                    for filename in files:
                        p = current_path / filename
                        try:
                            matches = p.suffix.casefold() == query_lower if extension_query else query_lower in filename.casefold()
                            if matches:
                                results.append({
                                    "name": filename, "path": str(p), "type": "file",
                                    "size": p.stat().st_size, "modified": p.stat().st_mtime
                                })
                        except (OSError, PermissionError):
                            continue
                    if len(results) >= 500:
                        break
            except (OSError, PermissionError) as exc:
                logger.debug("Search failed in %s: %s", root, exc)
            if len(results) >= 500:
                break

        results.sort(key=lambda item: (item.get("modified", 0), item["name"].casefold()), reverse=True)
        return results[:500]

    def find_recent_files(self, folder: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """Find recently modified files."""
        results = []
        search_folder = Path(folder) if folder else Path.home()
        cutoff = time.time() - (days * 86400)

        try:
            if not search_folder.exists():
                return results

            for file_path in search_folder.rglob('*'):
                if file_path.is_file() and file_path.stat().st_mtime > cutoff:
                    results.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "size": file_path.stat().st_size,
                        "modified": file_path.stat().st_mtime,
                    })

            results.sort(key=lambda x: x["modified"], reverse=True)

        except Exception as e:
            logger.error(f"Recent files error: {e}")

        return results

    # Folder operations
    def create_folder(self, path: str) -> Tuple[bool, str]:
        """Create a folder at the specified path."""
        try:
            folder = Path(path)
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Created folder: {path}"
        except Exception as e:
            return False, str(e)

    def create_nested_folder(self, base_path: str, folder_path: str) -> Tuple[bool, str]:
        """Create nested folders."""
        try:
            base = Path(base_path)
            full_path = base / folder_path
            full_path.mkdir(parents=True, exist_ok=True)
            return True, f"Created nested folder: {full_path}"
        except Exception as e:
            return False, str(e)

    # File operations
    def rename(self, old_path: str, new_path: str) -> Tuple[bool, str]:
        """Rename a file or folder."""
        try:
            old = Path(old_path)
            new = Path(new_path)
            if not old.exists():
                return False, f"Source not found: {old_path}"

            old.rename(new)
            return True, f"Renamed to: {new_path}"
        except Exception as e:
            return False, str(e)

    def copy_file(self, src: str, dst: str) -> Tuple[bool, str]:
        """Copy a file."""
        try:
            source = Path(src)
            destination = Path(dst)

            if not source.exists():
                return False, f"Source not found: {src}"

            # Check destination
            if destination.exists():
                # Ask user - for now, overwrite with confirmation disabled in auto mode
                pass

            shutil.copy2(str(source), str(destination))
            return True, f"Copied {src} to {dst}"
        except Exception as e:
            return False, str(e)

    def move_file(self, src: str, dst: str) -> Tuple[bool, str]:
        """Move a file."""
        try:
            source = Path(src)
            destination = Path(dst)

            if not source.exists():
                return False, f"Source not found: {src}"

            # Check destination size
            destination.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source), str(destination))
            return True, f"Moved {src} to {dst}"
        except Exception as e:
            return False, str(e)

    def read_file(self, path: str, max_bytes: int = 32 * 1024) -> Tuple[bool, str, Dict[str, Any]]:
        """Read a UTF-8 text file within the enabled access scope."""
        try:
            from alice.core.access_manager import ComputerAccessManager
            manager = ComputerAccessManager(self.config)
            allowed, reason = manager.validate_path(path)
            if not allowed:
                return False, reason, {"path": str(path)}
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists() or not file_path.is_file():
                return False, f"File not found: {file_path}", {"path": str(file_path)}
            size = file_path.stat().st_size
            if size > max_bytes:
                return False, f"File is {size} bytes; the read limit is {max_bytes} bytes.", {"path": str(file_path), "size": size}
            content = file_path.read_text(encoding="utf-8")
            return True, content, {"path": str(file_path), "size": size}
        except (UnicodeDecodeError, OSError, PermissionError) as exc:
            return False, str(exc), {"path": str(path)}

    def move_file(self, src: str, dst: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Move a file or folder without overwriting an existing destination."""
        try:
            from alice.core.access_manager import ComputerAccessManager
            manager = ComputerAccessManager(self.config)
            source = Path(src).expanduser().resolve()
            destination = Path(dst).expanduser().resolve()
            if not source.exists():
                return False, f"Source not found: {source}", {"source": str(source)}
            # A directory destination means "move into this folder", preserving
            # the source name. An existing file is never overwritten.
            if destination.exists() and destination.is_dir():
                destination = destination / source.name
            for candidate in (source, destination):
                allowed, reason = manager.validate_path(candidate)
                if not allowed:
                    return False, reason, {"source": str(source), "destination": str(destination)}
            if manager.protected_destructive_path(source) or manager.protected_destructive_path(destination):
                return False, "Refusing to move from or into a protected system location.", {"source": str(source), "destination": str(destination)}
            if source.is_dir() and is_within(destination, source):
                return False, "Cannot move a folder into itself or one of its descendants.", {"source": str(source), "destination": str(destination)}
            if destination.exists():
                return False, f"Destination already exists; refusing to overwrite: {destination}", {"destination": str(destination)}
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            return True, f"Moved {source} to {destination}", {"source": str(source), "destination": str(destination)}
        except (OSError, PermissionError, shutil.Error) as exc:
            return False, str(exc), {"source": str(src), "destination": str(dst)}

    # ZIP operations
    def extract_zip(self, archive_path: str, destination: Optional[str] = None) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Extract a ZIP archive with contents listing."""
        results = []
        try:
            archive = Path(archive_path)

            if not archive.exists():
                return False, f"Archive not found: {archive_path}", results

            # Determine destination
            if destination:
                dest_path = Path(destination)
            else:
                dest_path = archive.parent

            dest_path.mkdir(parents=True, exist_ok=True)

            # List contents first
            with zipfile.ZipFile(str(archive), 'r') as zf:
                names = zf.namelist()

            # Extract
            with zipfile.ZipFile(str(archive), 'r') as zf:
                for name in names:
                    zf.extract(name, str(dest_path))
                    # Build result entry
                    extracted_path = dest_path / name
                    if extracted_path.exists():
                        results.append({
                            "name": name,
                            "path": str(extracted_path),
                            "size": extracted_path.stat().st_size if extracted_path.is_file() else 0,
                        })

            return True, f"Extracted {len(results)} files from {archive_path}", results

        except Exception as e:
            return False, str(e), results

    def get_archive_contents(self, archive_path: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """List archive contents without extracting."""
        results = []
        try:
            import zipfile
            archive = Path(archive_path)

            if not archive.exists():
                return False, results

            with zipfile.ZipFile(str(archive), 'r') as zf:
                for info in zf.infolist():
                    results.append({
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compressed_size,
                        "compress_type": info.compress_type,
                    })

            return True, results
        except Exception as e:
            return False, results

    # File info
    def get_file_info(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file/directory information."""
        try:
            p = Path(path)
            if not p.exists():
                return None

            if p.is_file():
                return {
                    "name": p.name,
                    "path": str(p),
                    "size": p.stat().st_size,
                    "modified": p.stat().st_mtime,
                    "extension": p.suffix,
                    "is_file": True,
                }
            elif p.is_dir():
                return {
                    "name": p.name,
                    "path": str(p),
                    "size": 0,  # Folder size
                    "modified": p.stat().st_mtime,
                    "extension": "",
                    "is_file": False,
                    "children": [c.name for c in p.iterdir()] if p.iterdir() else [],
                }
        except Exception as e:
            logger.error(f"Get file info error: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get file operations status."""
        return {
            "allowed_locations": self.allowed_locations,
        }

    def save_file(self, path: str, content: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Save content to a file. If content is None, uses clipboard content.

        Returns (success, message, details).
        """
        import time
        try:
            # Resolve path
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Get content - either provided or from clipboard
            if content is None or content == "${clipboard}":
                try:
                    import pyperclip
                    content = pyperclip.paste()
                except ImportError:
                    return False, "pyperclip not installed for clipboard access", {"path": str(file_path)}

            # Write content to file
            file_path.write_text(content, encoding='utf-8')
            time.sleep(0.1)  # Brief pause to ensure write completes

            # Verify file exists
            if file_path.exists():
                details = {
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "lines": len(content.splitlines()) if content else 0
                }
                return True, f"Saved file: {file_path}", details
            else:
                return False, f"File not found after save: {file_path}", {"path": str(file_path)}

        except Exception as e:
            logger.error(f"Save file error: {e}")
            return False, str(e), {"path": path}

    def delete_file(self, path: str, confirm: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
        """Delete a file.

        Args:
            path: Path to the file to delete
            confirm: Whether to require confirmation (for API consistency)

        Returns:
            Tuple of (success, message, details)
        """
        import time
        try:
            file_path = Path(path)

            if not file_path.exists():
                return False, f"File not found: {path}", {"path": str(file_path), "deleted": False}

            if not file_path.is_file():
                return False, f"Path is not a file: {path}", {"path": str(file_path), "deleted": False}

            original_size = file_path.stat().st_size
            file_path.unlink()
            time.sleep(0.1)  # Brief pause to ensure delete completes

            details = {
                "path": str(file_path),
                "deleted": True,
                "original_size": original_size
            }
            return True, f"Deleted file: {path}", details

        except Exception as e:
            logger.error(f"Delete file error: {e}")
            return False, str(e), {"path": str(path), "deleted": False}

    def delete_folder(self, path: str, recursive: bool = True, confirm: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
        """Delete a folder and its contents.

        Args:
            path: Path to the folder to delete
            recursive: Whether to delete contents recursively (always True for safety)
            confirm: Whether to require confirmation (for API consistency)

        Returns:
            Tuple of (success, message, details)
        """
        import time
        import shutil
        try:
            folder_path = Path(path)

            if not folder_path.exists():
                return False, f"Folder not found: {path}", {"path": str(folder_path), "deleted": False}

            if not folder_path.is_dir():
                return False, f"Path is not a folder: {path}", {"path": str(folder_path), "deleted": False}

            # Count items for reporting
            item_count = sum(1 for _ in folder_path.rglob('*')) if recursive else len(list(folder_path.iterdir()))

            # Always use recursive deletion for safety
            shutil.rmtree(str(folder_path))
            time.sleep(0.1)  # Brief pause to ensure delete completes

            details = {
                "path": str(folder_path),
                "deleted": True,
                "items_deleted": item_count
            }
            return True, f"Deleted folder: {path}", details

        except Exception as e:
            logger.error(f"Delete folder error: {e}")
            return False, str(e), {"path": str(path), "deleted": False}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from alice.core.config import Config

    config = Config.load()
    fo = FileOperations(config)

    # Test search
    results = fo.search_files(".pdf")
    print(f"PDF search results: {len(results)}")

    # Test folder creation
    success, msg = fo.create_folder("test_alcFolder")
    print(f"Folder creation: {success} - {msg}")

    # Test ZIP extraction (with a test ZIP if exists)
    success, msg, contents = fo.extract_zip("test.zip")
    print(f"ZIP extraction: {success} - {msg}, files: {len(contents)}")