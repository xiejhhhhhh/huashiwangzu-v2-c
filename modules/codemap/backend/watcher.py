"""Watchdog-based hot reload for the codemap index.

Monitors the three scan roots (backend/app, frontend/src, modules/*) for file
changes.  Events are debounced (500ms) and merged before triggering incremental
re-index of affected files.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .indexer import PROJECT_ROOT, SCAN_ROOTS, get_indexer

logger = logging.getLogger("v2.codemap").getChild("watcher")

_DEBOUNCE_SECONDS = 0.5


class DebouncedEventHandler:
    """Collects file change events and triggers incremental updates after a
    quiet period of _DEBOUNCE_SECONDS."""

    def __init__(self):
        try:
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            raise ImportError("watchdog is required for hot reload. pip install watchdog")
        self._handler: FileSystemEventHandler | None = None
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._indexer = get_indexer()

    def on_any_event(self, event) -> None:
        """Called by watchdog for any filesystem event."""
        # Ignore directory events
        if event.is_directory:
            return

        src_path = str(event.src_path)
        # Convert to project-relative path
        try:
            rel_path = str(Path(src_path).relative_to(PROJECT_ROOT))
        except ValueError:
            return

        # Only care about source files
        ext = Path(rel_path).suffix.lower()
        if ext not in (".py", ".ts", ".tsx", ".vue"):
            return

        with self._lock:
            self._pending.add(rel_path)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._flush)
            self._timer.start()

    def _flush(self) -> None:
        """Process all pending changes."""
        with self._lock:
            pending = self._pending.copy()
            self._pending.clear()
            self._timer = None

        for rel_path in pending:
            abs_path = PROJECT_ROOT / rel_path
            if abs_path.exists():
                logger.info("Hot update: %s (modified)", rel_path)
                self._indexer.update_file(rel_path)
            else:
                logger.info("Hot update: %s (deleted)", rel_path)
                self._indexer.remove_file(rel_path)


class FileWatcher:
    """Manages watchdog observer lifecycle."""

    def __init__(self):
        try:
            from watchdog.observers import Observer
        except ImportError:
            raise ImportError("watchdog is required for hot reload. pip install watchdog")
        from watchdog.observers import Observer
        self._observer = Observer()
        self._handler = DebouncedEventHandler()
        self._started = False

    def start(self) -> None:
        """Start watching the scan roots."""
        if self._started:
            return

        for root_name in SCAN_ROOTS:
            root_path = PROJECT_ROOT / root_name
            if not root_path.exists():
                logger.warning("Watch root not found: %s", root_path)
                continue
            try:
                from watchdog.events import FileSystemEventHandler

                # Create a simple handler that delegates to our debounced handler
                class _Handler(FileSystemEventHandler):
                    def on_created(self_h, event):
                        self._handler.on_any_event(event)

                    def on_modified(self_h, event):
                        self._handler.on_any_event(event)

                    def on_deleted(self_h, event):
                        self._handler.on_any_event(event)

                    def on_moved(self_h, event):
                        self._handler.on_any_event(event)

                self._observer.schedule(_Handler(), str(root_path), recursive=True)
                logger.info("Watching: %s", root_path)
            except Exception as exc:
                logger.error("Failed to watch %s: %s", root_path, exc)

        self._observer.start()
        self._started = True
        logger.info("File watcher started")

    def stop(self) -> None:
        """Stop the file watcher."""
        if not self._started:
            return
        self._observer.stop()
        self._observer.join(timeout=3)
        self._started = False
        logger.info("File watcher stopped")


# Singleton
_watcher_instance: FileWatcher | None = None


def get_watcher() -> FileWatcher:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = FileWatcher()
    return _watcher_instance
