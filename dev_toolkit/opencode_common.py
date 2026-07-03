"""Shared constants and helpers for opencode SDK tools.

Avoids code duplication between ``opencode_tools.py`` and ``opencode_queue.py``.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 55891
DEFAULT_SDK_PACKAGE = "@opencode-ai/sdk@1.17.13"
LOCAL_NO_PROXY = "127.0.0.1,localhost,::1"


def now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def logs_dir(repo_root: Path) -> Path:
    return repo_root / "backend" / "logs"


def sdk_dir(repo_root: Path) -> Path:
    return logs_dir(repo_root) / "opencode-sdk"


def sdk_script(repo_root: Path) -> Path:
    return repo_root / "dev_toolkit" / "opencode_sdk_client.mjs"


def safe_title(value: str) -> str:
    import re
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-. ]+", "", value.strip()).strip(" .")
    return cleaned[:120] or "opencode-dispatch"


def node_binary() -> str | None:
    return shutil.which("node")


def npm_binary() -> str | None:
    return shutil.which("npm")


def opencode_env(*, use_proxy: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = LOCAL_NO_PROXY
    env["no_proxy"] = LOCAL_NO_PROXY
    if use_proxy:
        proxy = "http://127.0.0.1:4780"
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    return env
