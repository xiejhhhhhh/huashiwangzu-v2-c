import asyncio
import logging
import time

import httpx

from app.gateway.config import get_models_config
from app.services.model_watchdog.launcher import kill_model, launch_model
from app.services.model_watchdog.registry import (
    ModelRecord,
    get_model,
    list_local_models,
    list_models,
)
from app.services.model_watchdog.runtime import (
    model_runtime_state,
    model_usage,
    should_reap_idle_model,
    touch_model,
)

logger = logging.getLogger("model_watchdog.watchdog")

_HEALTHY_CACHE: dict[str, bool] = {}


def _check_health(record: ModelRecord) -> bool:
    health_url = record.health_url()
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            resp = client.get(health_url)
            if _healthy_status(record, resp.status_code):
                return True
            logger.warning(
                "Model %s returned HTTP %d", record.name, resp.status_code
            )
            return False
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.debug("Model %s health check failed: %s", record.name, e)
        return False


def ensure_model(name: str) -> ModelRecord:
    record = get_model(name)

    if _HEALTHY_CACHE.get(name):
        touch_model(record)
        return record

    if _check_health(record):
        _HEALTHY_CACHE[name] = True
        touch_model(record)
        logger.info("Model %s is already healthy, skipping launch", name)
        return record

    if record.model_type == "cloud":
        raise ConnectionError(
            f"Cloud model '{record.name}' is not reachable "
            f"(endpoint: {record.endpoint}). "
            f"Check if your API key is valid or the subscription is active."
        )

    logger.info(
        "Model %s is down (port %d), launching...", record.name, record.port
    )
    launch_model(record)
    _HEALTHY_CACHE[name] = True
    touch_model(record)
    return record


def invalidate_cache(name: str | None = None) -> None:
    if name:
        _HEALTHY_CACHE.pop(name, None)
    else:
        _HEALTHY_CACHE.clear()


def use_model(name: str):
    record = get_model(name)
    return model_usage(record)


def reap_idle_models(now: float | None = None) -> dict[str, dict]:
    now = now or time.time()
    results: dict[str, dict] = {}
    for record in list_local_models():
        healthy = _check_health(record)
        state = model_runtime_state(record, now=now)
        if (
            healthy
            and record.auto_unload
            and record.idle_timeout_seconds > 0
            and state.get("last_used_at") is None
        ):
            touch_model(record)
            state = model_runtime_state(record, now=now)
            results[record.name] = {
                **state,
                "healthy_before": healthy,
                "reaped": False,
                "reason": "idle_timer_started",
            }
            continue
        should_reap, reason = should_reap_idle_model(record, now=now)
        if should_reap and healthy:
            logger.info(
                "Reaping idle model %s after %.1fs idle (timeout=%ss)",
                record.name,
                state.get("idle_seconds") or 0,
                record.idle_timeout_seconds,
            )
            kill_model(record)
            invalidate_cache(record.name)
            results[record.name] = {
                **state,
                "healthy_before": healthy,
                "reaped": True,
                "reason": reason,
            }
            continue
        if not healthy:
            invalidate_cache(record.name)
        results[record.name] = {
            **state,
            "healthy_before": healthy,
            "reaped": False,
            "reason": reason,
        }
    return results


async def idle_reaper_loop() -> None:
    defaults = get_models_config().get("watchdog_defaults", {})
    interval_seconds = float(defaults.get("idle_reap_interval_seconds", 30) or 30)
    interval_seconds = max(5.0, interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await asyncio.to_thread(reap_idle_models)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Model idle reaper failed: %s", exc)


def status_all() -> dict[str, bool]:
    results = {}
    for record in list_models():
        results[record.name] = _check_health(record)
    return results


def runtime_status_all() -> dict[str, dict]:
    results: dict[str, dict] = {}
    for record in list_models():
        healthy = _check_health(record)
        state = model_runtime_state(record)
        results[record.name] = {
            **state,
            "healthy": healthy,
            "ready": healthy,
            "state": "healthy" if healthy else state.get("startup", {}).get("state", "unknown"),
        }
    return results


def _healthy_status(record: ModelRecord, status_code: int) -> bool:
    if record.model_type == "local":
        return 200 <= status_code < 300
    return status_code < 500
