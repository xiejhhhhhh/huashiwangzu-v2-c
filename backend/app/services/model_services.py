"""
Config-driven embedding and rerank services.

Reads the active endpoint from models.json — that's the single source of truth.
During development, configure the URL that works; the code doesn't auto-probe.
"""

import json
import logging
from asyncio import to_thread
from pathlib import Path

import httpx

from app.services.model_watchdog.watchdog import ensure_model

logger = logging.getLogger("v2.model_services")

# Path: backend/app/services/model_services.py → backend/data/config/models.json
_MODELS_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "config" / "models.json"
)

_CONFIG_CACHE: dict | None = None


def _get_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    with open(_MODELS_CONFIG_PATH) as f:
        _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE


def _embedding_profile() -> dict:
    cfg = _get_config()
    emb = cfg["model_types"]["embedding"]
    pk = emb.get("primary", "")
    if not pk:
        raise RuntimeError("No primary embedding model in models.json")
    return emb["profiles"][pk]


def _rerank_profile() -> dict:
    cfg = _get_config()
    rr = cfg["model_types"]["rerank"]
    pk = rr.get("primary", "")
    if not pk:
        raise RuntimeError("No primary rerank model in models.json")
    return rr["profiles"][pk]


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector from the configured endpoint (models.json)."""
    profile = _embedding_profile()

    watchdog_name = profile.get("watchdog")
    if watchdog_name:
        await to_thread(ensure_model, watchdog_name)

    server_url = profile.get("server_url", "")
    if not server_url:
        raise RuntimeError(f"No server_url in embedding profile: {profile}")

    model = profile.get("model", "bge-m3")
    adapter = profile.get("response_adapter", "openai_compat")
    url = f"{server_url.rstrip('/')}/v1/embeddings"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={
            "model": model,
            "input": [text[:2048]],
        })
        resp.raise_for_status()
        data = resp.json()

    # OpenAI-compatible response: {"data": [{"embedding": [...], "index": 0}], ...}
    emb_list = data.get("data", [])
    if not emb_list:
        raise RuntimeError(f"Empty embedding response from {url}: {data}")
    return emb_list[0]["embedding"]


async def rerank(
    query: str,
    documents: list[str],
    top_k: int | None = None,
) -> list[dict]:
    """Rerank documents by relevance, using the configured endpoint (models.json).
    
    Returns [{index, relevance_score}, ...] sorted by score descending.
    """
    if not documents:
        return []

    profile = _rerank_profile()

    watchdog_name = profile.get("watchdog")
    if watchdog_name:
        await to_thread(ensure_model, watchdog_name)

    server_url = profile.get("server_url", "")
    if not server_url:
        raise RuntimeError(f"No server_url in rerank profile: {profile}")

    model = profile.get("model", "bge-reranker-v2-m3")
    url = f"{server_url.rstrip('/')}/v1/rerank"

    payload: dict = {"model": model, "query": query, "documents": documents}
    if top_k is not None:
        payload["top_k"] = top_k

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    results.sort(key=lambda r: r.get("relevance_score", 0), reverse=True)
    return results


async def describe_image(
    image_bytes: bytes,
    prompt: str = "请详细描述这张图片",
    profile_key: str | None = None,
    mime_type: str = "image/jpeg",
) -> str:
    """Describe an image using the configured vision model (models.json).

    Delegates to the gateway router's describe_image, which handles
    vision profile resolution, fallback chain, and retry.
    """
    from app.gateway.router import gateway_router
    return await gateway_router.describe_image(
        image_bytes=image_bytes,
        prompt=prompt,
        profile_key=profile_key,
        mime_type=mime_type,
    )
