import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import AppException
from app.services.model_services import get_embedding as config_get_embedding

logger = logging.getLogger("v2.knowledge_service")

VECTOR_DIM = 1024


async def get_embedding(text: str) -> list[float]:
    try:
        return await config_get_embedding(text)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return []


from app.services.knowledge.retrieval.hybrid import hybrid_search as retrieval_hybrid_search


async def hybrid_search(db: AsyncSession, query: str, top_k: int = 10):
    return await retrieval_hybrid_search(db, query, top_k=top_k)
