"""
Config-driven embedding and rerank services.

Reads the active endpoint from models.json — that's the single source of truth.
During development, configure the URL that works; the code doesn't auto-probe.
"""

import logging
from asyncio import to_thread

import httpx

from app.gateway.config import get_model_type_config
from app.services.model_watchdog.watchdog import ensure_model, use_model

logger = logging.getLogger("v2.model_services")


def resolve_embedding_profile_key(profile_key: str | None = None) -> str:
    emb = get_model_type_config("embedding")
    pk = profile_key or emb.get("primary", "")
    if not pk:
        raise RuntimeError("No primary embedding model in models.json")
    if pk not in emb.get("profiles", {}):
        raise RuntimeError(f"Embedding profile not found in models.json: {pk}")
    return str(pk)


def get_embedding_profile_contract(profile_key: str | None = None) -> dict:
    """Return embedding profile metadata with the resolved profile key attached."""
    emb = get_model_type_config("embedding")
    pk = resolve_embedding_profile_key(profile_key)
    profile = dict(emb["profiles"][pk])
    profile["profile_key"] = pk
    return profile


def _embedding_profile(profile_key: str | None = None) -> dict:
    return get_embedding_profile_contract(profile_key)


def _rerank_profile() -> dict:
    rr = get_model_type_config("rerank")
    pk = rr.get("primary", "")
    if not pk:
        raise RuntimeError("No primary rerank model in models.json")
    return rr["profiles"][pk]


async def get_embeddings(texts: list[str], profile_key: str | None = None) -> list[list[float]]:
    """Get embedding vectors from the configured endpoint (models.json)."""
    if not texts:
        return []
    profile = _embedding_profile(profile_key)

    watchdog_name = profile.get("watchdog")
    if watchdog_name:
        await to_thread(ensure_model, watchdog_name)

    server_url = profile.get("server_url", "")
    if not server_url:
        raise RuntimeError(f"No server_url in embedding profile: {profile}")

    model = profile.get("model", "bge-m3")
    url = f"{server_url.rstrip('/')}/v1/embeddings"

    payload = {
        "model": model,
        "input": [str(text or "")[:2048] for text in texts],
    }
    if watchdog_name:
        with use_model(str(watchdog_name)):
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
    else:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

    # OpenAI-compatible response: {"data": [{"embedding": [...], "index": 0}], ...}
    emb_list = data.get("data", [])
    if not emb_list:
        raise RuntimeError(f"Empty embedding response from {url}: {data}")
    emb_list.sort(key=lambda item: int(item.get("index", 0)))
    return [item["embedding"] for item in emb_list]


async def get_embedding(text: str, profile_key: str | None = None) -> list[float]:
    """Get one embedding vector from the configured endpoint (models.json)."""
    embeddings = await get_embeddings([text], profile_key=profile_key)
    if not embeddings:
        raise RuntimeError("Empty embedding response")
    return embeddings[0]


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

    if watchdog_name:
        with use_model(str(watchdog_name)):
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
    else:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
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


async def describe_image_detailed(
    image_bytes: bytes,
    prompt: str = "请详细描述这张图片",
    profile_key: str | None = None,
    mime_type: str = "image/jpeg",
) -> dict:
    """Describe an image and return content plus gateway diagnostics."""
    from app.gateway.router import gateway_router
    return await gateway_router.describe_image_detailed(
        image_bytes=image_bytes,
        prompt=prompt,
        profile_key=profile_key,
        mime_type=mime_type,
    )
