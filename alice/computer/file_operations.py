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

logger = logging.getLogger(__name__)


class FileOperations:
    """Local file operations engine for ALICE."""

    def __init__(self, config: Any):
        self.config = config
        self.allowed_locations: List[str] = config.automation.allowed_locations

    # Search operations
    def search_files(self, query: str, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for files by name or extension within a folder.

        If no folder is specified, searches across all allowed locations.
        """
        results = []
        query_lower = query.lower()

        # Determine search locations: specific folder or all allowed locations
        if folder:
            search_locations = [Path(folder)]
        else:
            search_locations = [Path(loc) for loc in self.allowed_locations if Path(loc).exists()]

        for search_folder in search_locations:
            # Restrict to allowed locations
            if str(search_folder) not in self.allowed_locations:
                logger.warning(f"Search folder {search_folder} not in allowed locations")
                continue

            try:
                if not search_folder.exists():
                    continue

                # If query looks like an extension (starts with .)
                if query_lower.startswith('.'):
                    ext = query_lower
                    for file_path in search_folder.rglob('*'):
                        if file_path.is_file() and file_path.suffix.lower() == ext:
                            results.append({
                                "name": file_path.name,
                                "path": str(file_path),
                                "size": file_path.stat().st_size,
                                "modified": file_path.stat().st_mtime,
                            })
                else:
                    # Search by name pattern
                    for file_path in search_folder.rglob('*'):
                        if file_path.is_file() and query_lower in file_path.name.lower():
                            results.append({
                                "name": file_path.name,
                                "path": str(file_path),
                                "size": file_path.stat().st_size,
                                "modified": file_path.stat().st_mtime,
                            })

            except Exception as e:
                logger.error(f"Search error in {search_folder}: {e}")

        # Sort by modification time, newest first, then by name for consistency
        results.sort(key=lambda x: (x["modified"], x["name"]), reverse=True)

        return results

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