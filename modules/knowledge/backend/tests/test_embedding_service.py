"""Tests for knowledge chunk embedding fallback behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-embedding-service")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from modules.knowledge.backend.services import embedding_service


@pytest.fixture(autouse=True)
def _reset_embedding_breaker() -> None:
    embedding_service._embedding_disabled_until = 0.0
    embedding_service._embedding_disabled_reason = ""


@pytest.mark.asyncio
async def test_chunk_and_embed_batches_embedding_requests(monkeypatch) -> None:
    calls: list[list[str]] = []

    async def fake_get_embeddings(texts: list[str], profile_key: str | None = None) -> list[list[float]]:
        calls.append(texts)
        return [[float(index)] * 1024 for index, _ in enumerate(texts)]

    monkeypatch.setattr(embedding_service, "get_embeddings", fake_get_embeddings)

    chunks = await embedding_service.chunk_and_embed(
        document_id=1,
        owner_id=2,
        blocks=[{"type": "paragraph", "text": f"chunk text {index}"} for index in range(7)],
    )

    assert [len(call) for call in calls] == [5, 2]
    assert len(chunks) == 7
    assert chunks[0]["embedding"] == [0.0] * 1024
    assert chunks[5]["embedding"] == [0.0] * 1024


@pytest.mark.asyncio
async def test_chunk_and_embed_stops_after_embedding_service_unavailable(monkeypatch) -> None:
    calls = 0

    async def unavailable_get_embeddings(texts: list[str], profile_key: str | None = None) -> list[list[float]]:
        nonlocal calls
        calls += 1
        raise FileNotFoundError(
            "llama.cpp server binary is not configured. Set LLAMA_CPP_SERVER_BIN "
            "or local_bin.llama_server in models.json."
        )

    monkeypatch.setattr(embedding_service, "get_embeddings", unavailable_get_embeddings)

    chunks = await embedding_service.chunk_and_embed(
        document_id=1,
        owner_id=2,
        blocks=[{"type": "paragraph", "text": f"chunk text {index}"} for index in range(12)],
    )

    assert calls == 1
    assert len(chunks) == 12
    assert all(chunk["embedding"] is None for chunk in chunks)


@pytest.mark.asyncio
async def test_chunk_and_embed_uses_cached_unavailable_state(monkeypatch) -> None:
    calls = 0

    async def fake_get_embeddings(texts: list[str], profile_key: str | None = None) -> list[list[float]]:
        nonlocal calls
        calls += 1
        return [[1.0] * 1024 for _ in texts]

    monkeypatch.setattr(embedding_service, "get_embeddings", fake_get_embeddings)
    embedding_service._remember_legacy_embedding_unavailable("missing llama-server")

    chunks = await embedding_service.chunk_and_embed(
        document_id=1,
        owner_id=2,
        blocks=[{"type": "paragraph", "text": "chunk text"}],
    )

    assert calls == 0
    assert len(chunks) == 1
    assert chunks[0]["embedding"] is None
