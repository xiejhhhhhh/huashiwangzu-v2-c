"""Fast local system diagnostics for the project toolkit."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

TOOL_NAMES = {"system_resource_snapshot"}


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="system_resource_snapshot",
            description="快速查看本机 CPU/内存/GPU(可用时)与项目相关进程资源占用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "process_limit": {
                        "type": "integer",
                        "description": "返回项目相关进程数量上限",
                        "default": 12,
                    },
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name != "system_resource_snapshot":
        raise ValueError(f"未知系统工具: {name}")
    process_limit = int(arguments.get("process_limit", 12) or 12)
    snapshot = await asyncio.to_thread(_snapshot, repo_root, max(0, process_limit))
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _snapshot(repo_root: Path, process_limit: int) -> dict[str, Any]:
    started = time.monotonic()
    cpu = _cpu_snapshot()
    memory = _memory_snapshot()
    gpu = _gpu_snapshot()
    processes = _project_processes(repo_root, process_limit)
    return {
        "success": True,
        "duration_seconds": round(time.monotonic() - started, 3),
        "cpu": cpu,
        "memory": memory,
        "gpu": gpu,
        "project_processes": processes,
    }


def _cpu_snapshot() -> dict[str, Any]:
    psutil = _import_psutil()
    if psutil is not None:
        return {
            "source": "psutil",
            "percent": psutil.cpu_percent(interval=0.2),
            "logical_cores": psutil.cpu_count(logical=True),
            "physical_cores": psutil.cpu_count(logical=False),
            "load_avg": list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else None,
        }
    try:
        out = subprocess.run(["top", "-l", "1", "-n", "0"], capture_output=True, text=True, timeout=3).stdout
    except Exception as exc:
        return {"source": "top", "percent": None, "error": str(exc)}
    line = next((item for item in out.splitlines() if item.startswith("CPU usage:")), "")
    return {"source": "top", "percent": _parse_top_cpu_percent(line), "raw": line}


def _memory_snapshot() -> dict[str, Any]:
    psutil = _import_psutil()
    if psutil is not None:
        mem = psutil.virtual_memory()
        return {
            "source": "psutil",
            "percent": mem.percent,
            "total_gb": round(mem.total / 1024**3, 2),
            "used_gb": round(mem.used / 1024**3, 2),
            "available_gb": round(mem.available / 1024**3, 2),
        }
    total_bytes = _sysctl_int("hw.memsize")
    vm = _vm_stat()
    if not total_bytes or not vm:
        return {"source": "sysctl/vm_stat", "percent": None}
    page_size = vm.get("page_size", 4096)
    free_pages = vm.get("Pages free", 0) + vm.get("Pages inactive", 0)
    available = free_pages * page_size
    used = max(0, total_bytes - available)
    return {
        "source": "sysctl/vm_stat",
        "percent": round(used / total_bytes * 100, 1),
        "total_gb": round(total_bytes / 1024**3, 2),
        "used_gb": round(used / 1024**3, 2),
        "available_gb": round(available / 1024**3, 2),
    }


def _gpu_snapshot() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.strip()
            gpus = []
            for line in out.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) >= 4:
                    gpus.append(
                        {
                            "utilization_percent": _to_float(parts[0]),
                            "memory_used_mb": _to_float(parts[1]),
                            "memory_total_mb": _to_float(parts[2]),
                            "name": parts[3],
                        }
                    )
            return {"source": "nvidia-smi", "available": True, "devices": gpus}
        except Exception as exc:
            return {"source": "nvidia-smi", "available": False, "error": str(exc)}
    if shutil.which("powermetrics"):
        return {
            "source": "powermetrics",
            "available": False,
            "utilization_percent": None,
            "note": "macOS GPU实时利用率通常需要 sudo powermetrics；MCP 工具不提权采样，避免卡住或弹权限。",
        }
    return {"source": "unavailable", "available": False, "utilization_percent": None}


def _project_processes(repo_root: Path, limit: int) -> list[dict[str, Any]]:
    psutil = _import_psutil()
    if psutil is None or limit <= 0:
        return []
    root = str(repo_root)
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info", "status"]):
        try:
            info = proc.info
            cmdline = " ".join(info.get("cmdline") or [])
            if root not in cmdline and not _looks_project_process(cmdline):
                continue
            memory_info = info.get("memory_info")
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "status": info.get("status"),
                    "cpu_percent": info.get("cpu_percent"),
                    "rss_mb": round((memory_info.rss if memory_info else 0) / 1024**2, 1),
                    "cmdline": cmdline[:240],
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda item: (item.get("rss_mb") or 0, item.get("cpu_percent") or 0), reverse=True)
    return rows[:limit]


def _looks_project_process(cmdline: str) -> bool:
    needles = (
        "uvicorn app.main:app",
        "task_worker_main",
        "dev_toolkit/server.py",
        "vite",
        "postgres",
    )
    return any(needle in cmdline for needle in needles)


def _import_psutil() -> Any | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil


def _parse_top_cpu_percent(line: str) -> float | None:
    if not line:
        return None
    marker = "% idle"
    if marker not in line:
        return None
    before = line.split(marker, 1)[0].split(",")[-1].strip()
    try:
        idle = float(before)
    except ValueError:
        return None
    return round(max(0.0, 100.0 - idle), 1)


def _sysctl_int(name: str) -> int | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=2).stdout.strip()
        return int(out)
    except Exception:
        return None


def _vm_stat() -> dict[str, int]:
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return {}
    data: dict[str, int] = {}
    for line in out.splitlines():
        if line.startswith("Mach Virtual Memory Statistics"):
            if "page size of" in line:
                raw = line.split("page size of", 1)[1].split("bytes", 1)[0].strip()
                data["page_size"] = int(raw)
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = int(value.strip().strip(".").replace(".", ""))
    return data


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
