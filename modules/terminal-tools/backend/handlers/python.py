"""Python execution and chart generation capabilities for terminal-tools.

Capabilities:
  terminal-tools:run_python — Run Python code in user workspace
  terminal-tools:chart      — Simplified chart generation
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from .sandbox import (
    _resolve_user_id,
    _user_workspace,
    _build_sandbox_profile,
    _safe_env,
    _DEFAULT_TIMEOUT,
    _MAX_OUTPUT_BYTES,
)

logger = logging.getLogger("v2.terminal-tools").getChild("handlers.python")

_CHART_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


def _build_python_exec_script(code: str, workspace_dir: str) -> str:
    return f"""import os, sys, io, json

os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg")

os.chdir({json.dumps(workspace_dir)})
sys.path.insert(0, {json.dumps(workspace_dir)})

{code}
"""


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:run_python
# ═══════════════════════════════════════════════════════════════════════
async def _run_python(params: dict, caller: str) -> dict:
    """Run Python code with pandas/numpy/matplotlib in user workspace.

    Reuses terminal-tools workspace isolation, timeout, and output truncation.
    Uses sandbox-exec on macOS (same as _exec), fail-closed on other platforms.
    Automatically collects plt.savefig() charts and uploads them to framework FS.
    """
    user_id = _resolve_user_id(caller)
    workspace = _user_workspace(user_id)
    workspace_real = str(workspace.resolve())
    code = params.get("code", "").strip()
    timeout = int(params.get("timeout", _DEFAULT_TIMEOUT))

    if not code:
        return {"success": False, "error": "No code provided"}
    if timeout <= 0 or timeout > 600:
        timeout = _DEFAULT_TIMEOUT

    input_file_ids = params.get("input_files", []) or []
    if input_file_ids:
        for fid in input_file_ids:
            file_id = int(fid)
            from app.database import AsyncSessionLocal
            from app.services.file_service import check_file_access
            from app.services.file_preview_service import _resolve_storage_path
            from app.core.exceptions import NotFound, AppException
            async with AsyncSessionLocal() as db:
                try:
                    file_record = await check_file_access(db, file_id, user_id)
                except (NotFound, AppException) as exc:
                    return {"success": False, "error": f"Input file {file_id} access denied: {exc}"}
                src_path = _resolve_storage_path(file_record)
                if not src_path or not src_path.exists():
                    return {"success": False, "error": f"Input file {file_id} not found on disk"}
                target_name = f"{file_record.name}.{file_record.extension}" if file_record.extension else file_record.name
                target = workspace / target_name
                shutil.copy2(str(src_path), str(target))

    run_id = uuid.uuid4().hex[:12]
    run_dir = workspace / f".da_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    script_content = _build_python_exec_script(code, str(run_dir))
    script_path = run_dir / "script.py"
    script_path.write_text(script_content, encoding="utf-8")

    safe_env = _safe_env(str(workspace_real))
    safe_env["MPLBACKEND"] = "Agg"
    safe_env["PYTHONDONTWRITEBYTECODE"] = "1"

    logger.info("user=%s run_python (timeout=%ss, input_files=%s)", user_id, timeout, input_file_ids)

    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = _build_sandbox_profile(workspace_real)
        argv = ["sandbox-exec", "-p", profile, sys.executable, str(script_path)]
        cwd = str(run_dir)
    else:
        return {
            "success": False,
            "error": "当前平台无可用沙盒(sandbox-exec)，run_python 已禁用。需要 macOS 或安装了 bubblewrap 的 Linux。",
            "code_preview": code[:200],
        }

    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, env=safe_env,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(str(run_dir), ignore_errors=True)
        return {"success": False, "error": f"Execution timed out after {timeout}s", "timed_out": True, "stdout": "", "stderr": f"Timeout after {timeout}s"}
    except Exception as exc:
        shutil.rmtree(str(run_dir), ignore_errors=True)
        return {"success": False, "error": f"Execution failed: {exc}", "stdout": "", "stderr": str(exc)}

    charts = []
    for fpath in run_dir.iterdir():
        if fpath.is_file() and fpath.suffix.lower() in _CHART_EXTENSIONS:
            try:
                file_bytes = fpath.read_bytes()
                from app.database import AsyncSessionLocal
                from app.services import file_upload_service
                async with AsyncSessionLocal() as db:
                    result = await file_upload_service.upload_file(
                        db, io.BytesIO(file_bytes), fpath.name, user_id, None,
                    )
                    charts.append({
                        "file_id": result["id"],
                        "name": result["name"],
                        "size": result["size"],
                        "deduplicated": result.get("deduplicated", False),
                    })
            except Exception as exc:
                logger.warning("user=%s failed to upload chart %s: %s", user_id, fpath.name, exc)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    stdout_truncated = len(stdout) > _MAX_OUTPUT_BYTES
    stderr_truncated = len(stderr) > _MAX_OUTPUT_BYTES
    if stdout_truncated:
        stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n... [stdout truncated at 1MB]"
    if stderr_truncated:
        stderr = stderr[:_MAX_OUTPUT_BYTES] + "\n... [stderr truncated at 1MB]"

    shutil.rmtree(str(run_dir), ignore_errors=True)

    return {
        "success": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "charts": charts,
        "chart_count": len(charts),
    }


# ═══════════════════════════════════════════════════════════════════════
# Capability: terminal-tools:chart
# ═══════════════════════════════════════════════════════════════════════
async def _chart(params: dict, caller: str) -> dict:
    """Foolproof chart generation: sends data + chart_type, gets a chart file."""
    data = params.get("data", [])
    chart_type = params.get("chart_type", "line")
    title = params.get("title", "")
    x_label = params.get("x_label", "")
    y_label = params.get("y_label", "")

    if not data:
        return {"success": False, "error": "No data provided"}
    if chart_type not in ("line", "bar", "pie"):
        return {"success": False, "error": f"Unsupported chart type: {chart_type}"}

    script_lines = [
        "import matplotlib",
        'matplotlib.use("Agg")',
        "import matplotlib.pyplot as plt",
        "import json",
        "",
        f"data = {json.dumps(data)}",
        f"title = {json.dumps(title)}",
        f"x_label = {json.dumps(x_label)}",
        f"y_label = {json.dumps(y_label)}",
        "",
    ]

    if chart_type == "pie":
        script_lines.extend([
            "labels = [str(d.get('x', d.get('label', ''))) for d in data]",
            "values = [float(d.get('y', d.get('value', 0))) for d in data]",
            "fig, ax = plt.subplots(figsize=(10, 8))",
            "ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)",
            "ax.axis('equal')",
        ])
    elif chart_type in ("line", "bar"):
        script_lines.extend([
            "xs = [str(d.get('x', '')) for d in data]",
            "ys = [float(d.get('y', 0)) for d in data]",
            "fig, ax = plt.subplots(figsize=(12, 6))",
        ])
        if chart_type == "line":
            script_lines.extend([
                "ax.plot(xs, ys, marker='o', linewidth=2, markersize=6)",
                "ax.grid(True, linestyle='--', alpha=0.6)",
            ])
        else:
            script_lines.extend([
                "ax.bar(xs, ys, color='#2395bc', edgecolor='white', linewidth=0.5)",
            ])

    script_lines.extend([
        "if title:",
        "    ax.set_title(title, fontsize=14, pad=15)",
        "if x_label:",
        "    ax.set_xlabel(x_label)",
        "if y_label:",
        "    ax.set_ylabel(y_label)",
        "",
        "plt.xticks(rotation=45, ha='right')",
        "plt.tight_layout()",
        'plt.savefig("chart.png", dpi=150)',
        'print(f"Chart saved: chart.png")',
    ])

    script = "\n".join(script_lines)
    exec_params = {"code": script, "timeout": 30}
    return await _run_python(exec_params, caller)
