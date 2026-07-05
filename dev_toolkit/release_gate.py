"""Compatibility CLI entrypoint for the release gate package."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_toolkit.release_gate import cli_main

if __name__ == "__main__":
    cli_main()
