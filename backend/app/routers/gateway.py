import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.gateway.config import DEFAULT_MODEL
from app.gateway.router import gateway_router
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.model_services import describe_image as describe_image_service
from app.services.model_services import get_embeddings
from app.services.model_services import rerank as rerank_service

logger = logging.getLogger("v2.gateway.api")
router = APIRouter(prefix="/api/gateway", tags=["gateway"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    profile_key: str = DEFAULT_MODEL
    tools: list[dict] | None = None


class EmbeddingRequest(BaseModel):
    texts: list[str]
    model: str | None = None
    profile_key: str | None = None


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_k: int | None = None


class DescribeImageRequest(BaseModel):
    image_base64: str  # base64-encoded image bytes (without data: prefix)
    prompt: str = "请详细描述这张图片"
    profile_key: str | None = None
    mime_type: str = "image/jpeg"


@router.get("/models")
async def list_models(user: User = Depends(require_permission("viewer"))):
    return ApiResponse(data=gateway_router.list_profiles())


@router.get("/health")
async def health(user: User = Depends(require_permission("viewer"))):
    result = await gateway_router.check_all_health()
    return ApiResponse(data=result)


@router.post("/chat")
async def chat(payload: ChatRequest, user: User = Depends(require_permission("viewer"))):
    messages = [m.model_dump() for m in payload.messages]
    result = await gateway_router.chat(
        messages=messages, profile_key=payload.profile_key, tools=payload.tools,
    )
    return ApiResponse(data=result)


@router.post("/chat-stream")
async def chat_stream(payload: ChatRequest, user: User = Depends(require_permission("viewer"))):
    messages = [m.model_dump() for m in payload.messages]

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async for event in gateway_router.chat_stream(
                messages=messages, profile_key=payload.profile_key, tools=payload.tools,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        except Exception as exc:
            logger.error("chat_stream failed: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/embedding")
async def embedding(payload: EmbeddingRequest, user: User = Depends(require_permission("viewer"))):
    profile_key = payload.profile_key or payload.model
    embeddings = await get_embeddings(payload.texts, profile_key=profile_key)
    return ApiResponse(data={"embeddings": embeddings, "count": len(embeddings)})


@router.post("/rerank")
async def rerank(payload: RerankRequest, user: User = Depends(require_permission("viewer"))):
    results = await rerank_service(payload.query, payload.documents, payload.top_k)
    normalized = [
        {"index": r.get("index"), "score": r.get("relevance_score", r.get("score", 0))}
        for r in results
    ]
    return ApiResponse(data={"results": normalized})


@router.post("/describe-image")
async def describe_image(payload: DescribeImageRequest, user: User = Depends(require_permission("viewer"))):
    import base64
    image_bytes = base64.b64decode(payload.image_base64)
    description = await describe_image_service(
        image_bytes=image_bytes,
        prompt=payload.prompt,
        profile_key=payload.profile_key,
        mime_type=payload.mime_type,
    )
    return ApiResponse(data={"description": description})
