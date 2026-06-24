"""Path security — shared path traversal protection helpers.

Validates that resolved paths stay within an allowed root directory.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("v2.path_security")


def validate_within_dir(path: str | Path, root: str | Path) -> None:
    """Ensure *path* resolves to a location within *root*.

    Raises ValueError with a safe (non-leaky) message if the path escapes.
    Uses Path.resolve() to follow symlinks and normalize .. components.
    """
    root_resolved = Path(root).resolve()
    try:
        target = Path(path).resolve()
        target.relative_to(root_resolved)
    except (ValueError, OSError, RuntimeError) as exc:
        logger.warning("Path escape detected: %s (root=%s)", exc, root_resolved)
        raise ValueError(f"Path is outside the allowed workspace boundary") from exc


def has_traversal_component(path_str: str) -> bool:
    """Return True if *path_str* contains parent-dir traversal components."""
    parts = Path(path_str).parts
    return ".." in parts


def safe_join(root: str | Path, *parts: str) -> Path:
    """Join path components under root and validate the result is within root."""
    candidate = Path(root).resolve()
    for part in parts:
        candidate = candidate / part
    validate_within_dir(candidate, root)
    return candidate
