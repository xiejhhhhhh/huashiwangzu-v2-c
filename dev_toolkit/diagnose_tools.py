"""一键诊断工具：聚合后端健康、数据库、系统资源、日志错误为结构化报告。"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from dev_toolkit.config_loader import load_config as _load_config
from dev_toolkit.log_tools import _detect_severity, _iter_log_files, _tail_lines
from dev_toolkit.system_tools import _snapshot

TOOL_NAMES = {"diagnose"}
_REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_BASE = _load_config(_REPO_ROOT).get("backend_base_url", "http://127.0.0.1:33000")


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="diagnose",
            description=(
                "一键诊断：同时检查后端健康、数据库连通性、系统资源、并按关键词/模块聚合错误日志。"
                "返回结构化诊断报告，适合快速定位问题根因。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "error_query": {
                        "type": "string",
                        "description": "可选：错误关键词过滤，如 analyze_image、VLM、timeout",
                        "default": "",
                    },
                    "module": {
                        "type": "string",
                        "description": "可选：聚焦诊断的模块名，如 agent、knowledge、media-intelligence",
                        "default": "",
                    },
                    "log_lines": {
                        "type": "number",
                        "description": "每个日志文件检查尾部行数",
                        "default": 100,
                    },
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "diagnose":
        return await _diagnose(
            repo_root,
            error_query=str(arguments.get("error_query", "")),
            module=str(arguments.get("module", "")),
            log_lines=int(arguments.get("log_lines", 100)),
        )
    raise ValueError(f"未知诊断工具: {name}")


async def _diagnose(
    repo_root: Path,
    error_query: str = "",
    module: str = "",
    log_lines: int = 100,
) -> str:
    checks: list[dict[str, Any]] = []
    started = time.monotonic()

    # ── 1. 后端健康 ──────────────────────────────────────
    health_result = await _check_health()
    checks.append(health_result)

    # ── 2. 数据库连通性 ──────────────────────────────────
    db_result = _check_database()
    checks.append(db_result)

    # ── 3. 系统资源 ──────────────────────────────────────
    resource_result = _check_resources(repo_root)
    checks.append(resource_result)

    # ── 4. 日志错误 ──────────────────────────────────────
    log_result = _scan_logs(repo_root, error_query, module, log_lines)
    checks.append(log_result)

    elapsed = round((time.monotonic() - started) * 1000)

    # ── 综合判定 ─────────────────────────────────────────
    failed = [c for c in checks if c.get("status") == "fail"]
    warnings_list = [c for c in checks if c.get("status") == "warn"]

    report: dict[str, Any] = {
        "success": len(failed) == 0,
        "duration_ms": elapsed,
        "summary": {
            "total_checks": len(checks),
            "passed": len(checks) - len(failed) - len(warnings_list),
            "warnings": len(warnings_list),
            "failed": len(failed),
        },
        "checks": checks,
    }

    if failed:
        report["recommendation"] = (
            f"发现 {len(failed)} 个失败项，建议先处理："
            + "; ".join(f"{c['name']}: {c.get('error', '未知错误')}" for c in failed)
        )
    elif warnings_list:
        report["recommendation"] = "全部核心检查通过，存在需要注意的警告。"
    else:
        report["recommendation"] = "系统运行正常。"

    return json.dumps(report, ensure_ascii=False, indent=2)


async def _check_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BACKEND_BASE}/api/health")
            data = resp.json() if resp.status_code == 200 else {"raw_status": resp.status_code}
        ok = isinstance(data, dict) and data.get("data", {}).get("status") == "ok"
        return {
            "name": "backend_health",
            "label": "后端健康",
            "status": "ok" if ok else "fail",
            "detail": data,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {
            "name": "backend_health",
            "label": "后端健康",
            "status": "fail",
            "error": str(exc),
        }


def _check_database() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["psql", "-U", "postgres", "-d", "huashiwangzu_v2", "-c", "SELECT 1 AS ok;", "-t", "-q"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "1" in result.stdout:
            return {"name": "database", "label": "数据库连通性", "status": "ok"}
        return {
            "name": "database", "label": "数据库连通性", "status": "fail",
            "error": result.stderr.strip() or "意外输出",
        }
    except FileNotFoundError:
        return {"name": "database", "label": "数据库连通性", "status": "warn", "error": "psql 未安装，跳过数据库检查"}
    except subprocess.TimeoutExpired:
        return {"name": "database", "label": "数据库连通性", "status": "fail", "error": "数据库连接超时"}
    except Exception as exc:
        return {"name": "database", "label": "数据库连通性", "status": "warn", "error": str(exc)}


def _check_resources(repo_root: Path) -> dict[str, Any]:
    try:
        snapshot = _snapshot(repo_root, process_limit=8)
        cpu = snapshot.get("cpu", {})
        mem = snapshot.get("memory", {})
        warnings_found = []
        cpu_percent = cpu.get("percent")
        if cpu_percent is not None and cpu_percent > 80:
            warnings_found.append(f"CPU {cpu_percent}% 偏高")
        mem_percent = mem.get("percent")
        if mem_percent is not None and mem_percent > 80:
            warnings_found.append(f"内存 {mem_percent}% 偏高")
        return {
            "name": "system_resources",
            "label": "系统资源",
            "status": "warn" if warnings_found else "ok",
            "detail": {
                "cpu_percent": cpu_percent,
                "memory_percent": mem_percent,
                "memory_available_mb": mem.get("available_mb"),
                "project_processes": len(snapshot.get("processes", [])),
            },
            "warnings": warnings_found,
        }
    except Exception as exc:
        return {"name": "system_resources", "label": "系统资源", "status": "warn", "error": str(exc)}


def _scan_logs(
    repo_root: Path,
    error_query: str,
    module: str,
    log_lines: int,
) -> dict[str, Any]:
    log_root = repo_root / "backend" / "logs"
    if not log_root.is_dir():
        return {"name": "log_errors", "label": "日志错误", "status": "warn", "error": "日志目录不存在"}

    sources = {"all"}
    if module:
        sources = {f"modules/{module}"}

    files = _iter_log_files(
        repo_root, sources=sources, module=module, include_archived=False,
    )

    errors: list[dict[str, Any]] = []
    warning_count = 0
    error_count = 0

    for file_info in files[:6]:  # 最多检查 6 个文件
        path = file_info.get("path")
        if not isinstance(path, Path):
            continue
        try:
            lines = _tail_lines(path, min(log_lines, 500))
        except OSError:
            continue
        file_errors = []
        for line in lines:
            if error_query and error_query.lower() not in line.lower():
                continue
            severity = _detect_severity(line)
            if severity in ("critical", "error"):
                file_errors.append(line[:300])
                error_count += 1
            elif severity == "warning":
                warning_count += 1
        if file_errors:
            errors.append({
                "file": str(path.relative_to(log_root) if log_root in path.parents else path.name),
                "size_bytes": file_info.get("size_bytes"),
                "error_samples": file_errors[:6],
                "total_errors_in_file": len(file_errors),
            })

    status = "ok"
    warnings_found = []
    if error_count > 0:
        status = "warn"
        warnings_found.append(f"发现 {error_count} 条错误")
    if warning_count > 0:
        warnings_found.append(f"发现 {warning_count} 条警告")

    return {
        "name": "log_errors",
        "label": "日志错误",
        "status": status,
        "detail": {
            "files_scanned": len(files),
            "error_count": error_count,
            "warning_count": warning_count,
            "query_filter": error_query or "(无)",
            "module_filter": module or "(全部)",
        },
        "errors": errors,
        "warnings": warnings_found,
    }
