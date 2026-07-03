"""Python execution and chart generation capabilities for terminal-tools.

Capabilities:
  terminal-tools:run_python — Run Python code in user workspace
  terminal-tools:chart      — Simplified chart generation
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import uuid

from .sandbox import (
    _DEFAULT_TIMEOUT,
    _build_sandbox_profile,
    _coerce_timeout,
    _resolve_user_id,
    _resolve_workspace_path,
    _run_process_capped,
    _safe_env,
    _safe_external_filename,
    _user_workspace,
    _workspace_relative_path,
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
    timeout = _coerce_timeout(params.get("timeout", _DEFAULT_TIMEOUT))

    if not code:
        return {"success": False, "error": "No code provided"}

    run_id = uuid.uuid4().hex[:12]
    run_dir = workspace / f".da_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        imported_files = []
        input_file_ids = params.get("input_files", []) or []
        if input_file_ids:
            for fid in input_file_ids:
                try:
                    file_id = int(fid)
                except (TypeError, ValueError):
                    return {"success": False, "error": f"Invalid input file id: {fid}"}
                if file_id <= 0:
                    return {"success": False, "error": f"Invalid input file id: {fid}"}
                from app.core.exceptions import AppException, NotFound
                from app.database import AsyncSessionLocal
                from app.services.file_preview_service import _resolve_storage_path
                from app.services.file_service import check_file_access
                async with AsyncSessionLocal() as db:
                    try:
                        file_record = await check_file_access(db, file_id, user_id)
                    except (NotFound, AppException) as exc:
                        return {"success": False, "error": f"Input file {file_id} access denied: {exc}"}
                    src_path = _resolve_storage_path(file_record)
                    if not src_path or not src_path.exists():
                        return {"success": False, "error": f"Input file {file_id} not found on disk"}
                    source_name = (
                        f"{file_record.name}.{file_record.extension}"
                        if file_record.extension else file_record.name
                    )
                    target_name = _safe_external_filename(source_name, f"input_{file_id}")
                    target = _resolve_workspace_path(user_id, f".da_{run_id}/{target_name}")
                    shutil.copy2(str(src_path), str(target))
                    imported_files.append(_workspace_relative_path(target, workspace))

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
                "error": "当前平台无可用沙盒(sandbox-exec)，run_python 已禁用。当前实现需要 macOS sandbox-exec。",
                "code_preview": code[:200],
            }

        result = _run_process_capped(argv, cwd, timeout, safe_env)
        if result["timed_out"]:
            return {
                "success": False,
                "error": f"Execution timed out after {timeout}s",
                "timed_out": True,
                "return_code": result["return_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "stdout_truncated": result["stdout_truncated"],
                "stderr_truncated": result["stderr_truncated"],
                "imported_files": imported_files,
            }
        if result["error"]:
            return {
                "success": False,
                "error": result["error"],
                "return_code": result["return_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "stdout_truncated": result["stdout_truncated"],
                "stderr_truncated": result["stderr_truncated"],
                "imported_files": imported_files,
            }

        charts = []
        chart_upload_errors = []
        for fpath in run_dir.iterdir():
            if fpath.is_file() and fpath.suffix.lower() in _CHART_EXTENSIONS:
                try:
                    from app.database import AsyncSessionLocal
                    from app.services import file_upload_service
                    async with AsyncSessionLocal() as db:
                        with fpath.open("rb") as chart_handle:
                            upload_result = await file_upload_service.upload_file(
                                db, chart_handle, fpath.name, user_id, None,
                            )
                        charts.append({
                            "file_id": upload_result["id"],
                            "name": upload_result["name"],
                            "size": upload_result["size"],
                            "deduplicated": upload_result.get("deduplicated", False),
                        })
                except Exception as exc:
                    chart_upload_errors.append({"name": fpath.name, "error": str(exc)})
                    logger.warning("user=%s failed to upload chart %s: %s", user_id, fpath.name, exc)

        return {
            "success": result["return_code"] == 0,
            "return_code": result["return_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "stdout_truncated": result["stdout_truncated"],
            "stderr_truncated": result["stderr_truncated"],
            "charts": charts,
            "chart_count": len(charts),
            "chart_upload_errors": chart_upload_errors,
            "imported_files": imported_files,
        }
    finally:
        shutil.rmtree(str(run_dir), ignore_errors=True)


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
    result = await _run_python(exec_params, caller)
    if result.get("success") and result.get("chart_count", 0) < 1:
        result["success"] = False
        result["error"] = "Chart generation produced no uploaded chart file"
    return result
