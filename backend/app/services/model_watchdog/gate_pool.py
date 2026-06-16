import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("model_watchdog.gate_pool")

MIMO_GATES: list[dict[str, Any]] = []
_GATE_HEALTH: dict[str, dict] = {}
CONSECUTIVE_FAIL_LIMIT = 2
DISABLE_SECONDS = 120
PER_GATE_MAX_CONCURRENT = 5


def init():
    global MIMO_GATES
    if MIMO_GATES:
        return
    cfg = get_settings()
    MIMO_GATES = [
        {"name": "gate1", "endpoint": "https://token-plan-cn.xiaomimimo.com/v1/chat/completions", "key": cfg.MIMO_GATE1_KEY, "model": "mimo-v2.5"},
    ]
    for g in MIMO_GATES:
        if g["name"] not in _GATE_HEALTH:
            _GATE_HEALTH[g["name"]] = {"failures": 0, "disabled_until": 0, "success": 0, "total_fail": 0, "active": 0}


def available(name: str) -> bool:
    h = _GATE_HEALTH.get(name)
    if not h:
        return False
    if h["disabled_until"] > time.time():
        return False
    if h["failures"] >= CONSECUTIVE_FAIL_LIMIT:
        h["disabled_until"] = time.time() + DISABLE_SECONDS
        return False
    if h["active"] >= PER_GATE_MAX_CONCURRENT:
        return False
    return True


def mark_success(name: str):
    h = _GATE_HEALTH.get(name)
    if h:
        h["failures"] = 0
        h["success"] += 1


def mark_fail(name: str, severe: bool = False):
    h = _GATE_HEALTH.get(name)
    if not h:
        return
    h["failures"] += 1
    h["total_fail"] += 1
    if severe or h["failures"] >= CONSECUTIVE_FAIL_LIMIT:
        h["disabled_until"] = time.time() + DISABLE_SECONDS
        logger.warning("Gate %s disabled for %ss (failures=%d)", name, DISABLE_SECONDS, h["failures"])


def call_single(gate: dict, messages: list, images: list[str] | None = None, timeout: int = 60) -> dict | None:
    h = _GATE_HEALTH.get(gate["name"])
    if h:
        h["active"] += 1
    try:
        body: dict[str, Any] = {"model": gate["model"], "messages": messages, "max_tokens": 4096}
        if images:
            content = [{"type": "text", "text": "描述这张图片"}]
            for img in images:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}})
            body["messages"] = [{"role": "user", "content": content}]
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(gate["endpoint"], json=body, headers={"Authorization": f"Bearer {gate['key']}"})
            if resp.status_code == 429:
                return None
            if resp.status_code >= 500:
                mark_fail(gate["name"], severe=True)
                return None
            data = resp.json()
            if data.get("choices") and data["choices"][0].get("message"):
                mark_success(gate["name"])
                return data
            mark_fail(gate["name"])
            return None
    except Exception as e:
        logger.debug("Gate %s error: %s", gate["name"], e)
        mark_fail(gate["name"])
        return None
    finally:
        if h:
            h["active"] -= 1


def call_parallel(messages: list, images: list[str] | None = None) -> dict | None:
    init()
    healthy = [g for g in MIMO_GATES if available(g["name"])]
    if not healthy:
        return None
    with ThreadPoolExecutor(max_workers=len(healthy)) as pool:
        fut_map = {pool.submit(call_single, g, messages, images): g for g in healthy}
        for f in as_completed(fut_map):
            result = f.result()
            if result:
                for other_f in fut_map:
                    if other_f != f:
                        other_f.cancel()
                return result
    return None


def probe_all() -> dict[str, bool]:
    init()
    results = {}
    for g in MIMO_GATES:
        ok = call_single(g, [{"role": "user", "content": "回复：通了"}], timeout=15) is not None
        results[g["name"]] = ok
        if not ok:
            mark_fail(g["name"], severe=True)
    return results


def status() -> dict:
    init()
    return {g["name"]: {
        "available": available(g["name"]),
        "failures": _GATE_HEALTH[g["name"]]["failures"],
        "disabled_until": _GATE_HEALTH[g["name"]]["disabled_until"],
        "success": _GATE_HEALTH[g["name"]]["success"],
        "total_fail": _GATE_HEALTH[g["name"]]["total_fail"],
    } for g in MIMO_GATES}
