"""系统资源统一底座(5秒缓存,毫秒读)。

病根:dispatcher / model_watchdog / system_status 三处各自现调 psutil 读整机资源,
GPU 还各写各的(powermetrics 要 sudo 又秒级)。收口成一个采样器:后台每 5 秒采一次,
落盘 /tmp 缓存;所有需要整机资源的地方读缓存(毫秒级),不再各自现调。

- CPU/内存:psutil
- GPU:macmon(Apple Silicon,IOReport,无需 sudo,毫秒级)。缺 macmon 时 GPU 字段为 None。
- 跨进程共享:缓存落盘 JSON,后端/ dispatcher / executor 各进程都读同一文件。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil

logger = logging.getLogger("v2.resource_monitor")

缓存路径 = Path(os.getenv("RESOURCE_CACHE_PATH", "/tmp/华世_资源缓存.json"))
采样间隔秒 = float(os.getenv("RESOURCE_SAMPLE_INTERVAL", "5"))
过期阈值秒 = float(os.getenv("RESOURCE_STALE_SECONDS", "15"))
_macmon路径 = shutil.which("macmon") or os.path.expanduser("~/.cargo/bin/macmon")


def _采一次GPU() -> dict[str, Any]:
    """调 macmon 采样一次 GPU(毫秒级)。缺 macmon 或失败返回 None 字段。"""
    if not os.path.exists(_macmon路径):
        return {"gpu_percent": None, "gpu_ram_percent": None, "gpu_source": "unavailable"}
    try:
        proc = subprocess.run(
            [_macmon路径, "pipe", "-s", "1"],
            capture_output=True, text=True, timeout=6,
        )
        line = (proc.stdout or "").strip().splitlines()[0]
        d = json.loads(line)
        gpu = d.get("gpu_usage") or [None, None]
        mem = d.get("memory") or {}
        ram_total = mem.get("ram_total") or 0
        ram_usage = mem.get("ram_usage") or 0
        return {
            "gpu_percent": round(float(gpu[1]) * 100, 1) if gpu[1] is not None else None,
            "gpu_freq_mhz": gpu[0],
            "gpu_ram_percent": round(ram_usage / ram_total * 100, 1) if ram_total else None,
            "gpu_power_w": round(float(d.get("gpu_power") or 0), 2),
            "gpu_source": "macmon",
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("macmon 采样失败: %s", exc)
        return {"gpu_percent": None, "gpu_ram_percent": None, "gpu_source": "error"}


def 采样一次() -> dict[str, Any]:
    """采整机资源一次(CPU/内存 psutil + GPU macmon)。"""
    mem = psutil.virtual_memory()
    snap = {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "memory_percent": float(mem.percent),
        "memory_available_mb": round(mem.available / (1024 * 1024), 2),
        "memory_total_mb": round(mem.total / (1024 * 1024), 2),
        "logical_cores": psutil.cpu_count(logical=True),
        "sampled_at": time.time(),
    }
    snap.update(_采一次GPU())
    return snap


def _原子写缓存(snap: dict[str, Any]) -> None:
    """原子落盘(先写临时文件再 rename),防读到半截。"""
    缓存路径.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(缓存路径.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, 缓存路径)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def 读缓存(默认现采: bool = True) -> dict[str, Any]:
    """毫秒级读缓存。缓存不存在/过期时:默认现采一次兜底(默认现采=True)。"""
    try:
        snap = json.loads(缓存路径.read_text(encoding="utf-8"))
        年龄 = time.time() - float(snap.get("sampled_at", 0))
        snap["stale"] = 年龄 > 过期阈值秒
        snap["age_seconds"] = round(年龄, 1)
        if snap["stale"] and 默认现采:
            snap = 采样一次()
            snap["stale"] = False
            snap["age_seconds"] = 0.0
        return snap
    except (OSError, json.JSONDecodeError, ValueError):
        if 默认现采:
            return 采样一次()
        return {"cpu_percent": None, "memory_percent": None, "gpu_percent": None, "stale": True}


_采样任务: asyncio.Task | None = None
_停止 = False


async def _采样循环() -> None:
    global _停止
    logger.info("资源底座采样器启动(间隔%.0fs,缓存%s,macmon=%s)", 采样间隔秒, 缓存路径, os.path.exists(_macmon路径))
    while not _停止:
        try:
            # 采样含同步 subprocess(macmon)+psutil,丢线程池执行,绝不阻塞事件循环(否则拖死后端+macmon超时)
            snap = await asyncio.to_thread(采样一次)
            _原子写缓存(snap)
        except Exception as exc:  # noqa: BLE001
            logger.warning("资源采样写盘失败: %s", exc)
        await asyncio.sleep(采样间隔秒)


def 启动采样器() -> None:
    """挂在后端 lifespan,常驻每 5 秒采样落盘。幂等。"""
    global _采样任务, _停止
    if _采样任务 is not None and not _采样任务.done():
        return
    _停止 = False
    _采样任务 = asyncio.create_task(_采样循环())


async def 停止采样器() -> None:
    global _停止
    _停止 = True
    if _采样任务 is not None:
        _采样任务.cancel()
        try:
            await _采样任务
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
