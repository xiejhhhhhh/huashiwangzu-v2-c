#!/usr/bin/env python3
"""OpenAI-compatible embedding server for local Qwen3-Embedding HF weights."""
from __future__ import annotations

import argparse
import time
from typing import Any

import torch
import torch.nn.functional as F
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModel, AutoTokenizer


class EmbeddingRequest(BaseModel):
    model: str = "Qwen/Qwen3-Embedding-8B"
    input: str | list[str]


class ServerState:
    def __init__(self, model_path: str, max_length: int) -> None:
        self.model_path = model_path
        self.max_length = max_length
        self.tokenizer: Any | None = None
        self.model: Any | None = None
        self.device = self._select_device()
        self.dtype = torch.float16 if self.device in {"mps", "cuda"} else torch.float32

    @staticmethod
    def _select_device() -> str:
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def load(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            trust_remote_code=True,
            padding_side="left",
        )
        self.model = AutoModel.from_pretrained(
            self.model_path,
            trust_remote_code=True,
            torch_dtype=self.dtype,
        )
        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _last_token_pool(last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if bool(left_padding):
            return last_hidden_states[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_states.shape[0]
        return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.load()
        assert self.tokenizer is not None
        assert self.model is not None
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.no_grad():
            outputs = self.model(**encoded)
            pooled = self._last_token_pool(outputs.last_hidden_state, encoded["attention_mask"])
            embeddings = F.normalize(pooled, p=2, dim=1)
        return embeddings.detach().cpu().float().tolist()


def create_app(state: ServerState) -> FastAPI:
    app = FastAPI(title="Qwen3 Embedding Server")

    @app.get("/v1/models")
    async def models() -> dict:
        return {
            "object": "list",
            "data": [{
                "id": "Qwen/Qwen3-Embedding-8B",
                "object": "model",
                "owned_by": "local",
            }],
        }

    @app.post("/v1/embeddings")
    async def embeddings(payload: EmbeddingRequest) -> dict:
        started = time.perf_counter()
        texts = payload.input if isinstance(payload.input, list) else [payload.input]
        vectors = state.embed([str(text or "") for text in texts])
        prompt_tokens = sum(len(str(text or "")) for text in texts)
        return {
            "object": "list",
            "model": payload.model,
            "data": [
                {"object": "embedding", "index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "total_tokens": prompt_tokens,
            },
            "diagnostics": {
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "device": state.device,
                "dimensions": len(vectors[0]) if vectors else 0,
            },
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--port", type=int, default=30004)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--max-length", type=int, default=8192)
    args = parser.parse_args()

    state = ServerState(model_path=args.model_path, max_length=args.max_length)
    app = create_app(state)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
