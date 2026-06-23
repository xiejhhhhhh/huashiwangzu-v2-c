"""engine与 memory 模块之间的薄客户端层。
通过框架跨模块通路调 memory 能力，不直读 memory 表。"""
import logging
from app.services.module_registry import call_capability

logger = logging.getLogger("v2.agent").getChild("engine.layered_memory")

MEMORY_FUSE_BUDGET_THRESHOLD = 2000  # token, 召回多条且预算紧时触发融合
MEMORY_RECALL_DEFAULT_LIMIT = 5


async def record(
    text: str,
    owner_id: int,
    tags: str | None = None,
    source: str = "auto-distill",
    conversation_id: int | None = None,
) -> dict:
    """保存一条记忆到 memory 模块。走框架跨模块通路。"""
    try:
        result = await call_capability(
            "memory", "save",
            {
                "text": text,
                "tags": tags,
                "source": source,
                "conversation_id": conversation_id,
            },
            caller="system:agent-engine",
            caller_role="admin",
        )
        return result
    except Exception as e:
        logger.warning("记一笔 failed (non-fatal): %s", e)
        return {"success": False, "error": str(e), "fallback": True}


async def recall(
    owner_id: int,
    query: str,
    limit: int = MEMORY_RECALL_DEFAULT_LIMIT,
    expand_chain: bool = False,
) -> list[dict]:
    """从 memory 模块语义召回记忆。走框架跨模块通路。

    返回列表，每项含 id/text/summary/similarity/tags/raw_id 等。
    失败退空列表。
    """
    try:
        result = await call_capability(
            "memory", "recall",
            {
                "query": query,
                "limit": limit,
                "expand_chain": expand_chain,
            },
            caller="system:agent-engine",
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            return result["data"]
        return []
    except Exception as e:
        logger.warning("召回记忆 failed (non-fatal): %s", e)
        return []


async def fuse(
    owner_id: int,
    query: str,
    memory_ids: list[int],
) -> str | None:
    """即时融合：调 memory.fuse 把多条记忆融成贴合查询的简报。

    返回融合文本，失败退 None。
    """
    if not memory_ids:
        return None
    try:
        result = await call_capability(
            "memory", "fuse",
            {"query": query, "ids": memory_ids},
            caller="system:agent-engine",
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            fused = result["data"].get("fused", "")
            if fused:
                return fused
        return None
    except Exception as e:
        logger.warning("即时融合 failed (non-fatal): %s", e)
        return None


async def trigger_dream(
    owner_id: int,
) -> dict:
    """触发生 memory 模块的 dream 自优化。fire-and-forget。"""
    try:
        result = await call_capability(
            "memory", "dream",
            {},
            caller="system:agent-engine",
            caller_role="admin",
        )
        return result if result else {}
    except Exception as e:
        logger.warning("触发dream failed (non-fatal): %s", e)
        return {}
