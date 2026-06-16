import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.model_watchdog.watchdog import ensure_model
from app.services.model_watchdog.gate_pool import call_parallel

logger = logging.getLogger("model_watchdog.router")


def _call_opencode_go(messages: list) -> dict | None:
    try:
        ensure_model("opencode-go")
        cfg = get_settings()
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://opencode.ai/zen/go/v1/chat/completions",
                json={"model": "deepseek-v4-flash", "messages": messages, "max_tokens": 8192},
                headers={"Authorization": f"Bearer {cfg.DEEPSEEK_API_KEY}"},
            )
            if resp.status_code < 500:
                return resp.json()
    except Exception as e:
        logger.warning("opencode-go failed: %s", e)
    return None


def _get_local_model_name(endpoint: str) -> str | None:
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{endpoint}/v1/models")
            if resp.status_code < 500:
                data = resp.json()
                for src in (data.get("data") or [], data.get("models") or []):
                    if src:
                        return src[0].get("id") or src[0].get("model")
    except Exception as e:
        logger.warning("Failed to get local model name: %s", e)
    return None


def _call_local(model_name: str, messages: list) -> dict | None:
    try:
        ensure_model(model_name)
        from app.services.model_watchdog.registry import get_model
        record = get_model(model_name)
        actual = _get_local_model_name(record.endpoint)
        if not actual:
            return None
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{record.endpoint}/v1/chat/completions",
                json={"model": actual, "messages": messages, "max_tokens": 4096},
            )
            if resp.status_code < 500:
                return resp.json()
    except Exception as e:
        logger.warning("Local %s failed: %s", model_name, e)
    return None


def chat_completion(messages: list, **kwargs: Any) -> dict:
    chains = [
        ("mimo gates", lambda: call_parallel(messages)),
        ("opencode-go", lambda: _call_opencode_go(messages)),
        ("gemma-4 local", lambda: _call_local("gemma-4", messages)),
    ]
    for name, fn in chains:
        logger.info("Tier: %s", name)
        result = fn()
        if result:
            return result
        logger.warning("Fallback from %s", name)
    raise RuntimeError("All text model tiers exhausted")


def vision_analysis(messages: list, images: list[str], **kwargs: Any) -> dict:
    chains = [
        ("mimo gates vision", lambda: call_parallel(messages, images)),
        ("qwen3-vl local", lambda: _call_local("qwen3-vl", messages)),
    ]
    for name, fn in chains:
        logger.info("Vision tier: %s", name)
        result = fn()
        if result:
            return result
        logger.warning("Vision fallback from %s", name)
    raise RuntimeError("All vision model tiers exhausted")
