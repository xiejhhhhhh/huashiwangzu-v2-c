import logging

import httpx

from app.services.model_watchdog.launcher import launch_model
from app.services.model_watchdog.registry import (
    ModelRecord,
    get_model,
    list_models,
)

logger = logging.getLogger("model_watchdog.watchdog")

_HEALTHY_CACHE: dict[str, bool] = {}


def _check_health(record: ModelRecord) -> bool:
    health_url = record.health_url()
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            resp = client.get(health_url)
            if resp.status_code < 500:
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
        return record

    if _check_health(record):
        _HEALTHY_CACHE[name] = True
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
    return record


def invalidate_cache(name: str | None = None) -> None:
    if name:
        _HEALTHY_CACHE.pop(name, None)
    else:
        _HEALTHY_CACHE.clear()


def status_all() -> dict[str, bool]:
    results = {}
    for record in list_models():
        results[record.name] = _check_health(record)
    return results
