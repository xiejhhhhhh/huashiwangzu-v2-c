"""engine与 memory 模块之间的薄客户端层。
通过框架跨模块通路调 memory 能力，不直读 memory 表。

提供四层记忆体系：
  - Static file: 零延迟确定性记忆（文件读取，不依赖 DB/向量）
  - Stable rules: 持久规则/偏好/约束 (DB查询，不依赖向量)
  - Chunks: 带来源证明的段落级记忆 (语义召回)
  - Semantic: 原有关联链记忆 (语义召回)

静态记忆层（Layer 0）从 ``data/static-memory/`` 目录读取 markdown 文件，
每轮上下文装配时直接注入 system prompt，零延迟、零依赖。
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.module_registry import call_capability
from ..models import AgentRecallQuality as RecallQualityModel

logger = logging.getLogger("v2.agent").getChild("engine.layered_memory")

MEMORY_FUSE_BUDGET_THRESHOLD = 2000  # token, 召回多条且预算紧时触发融合
MEMORY_RECALL_DEFAULT_LIMIT = 5

# ── Recall quality governance (persisted via DB) ─────────────────────

_RECALL_QUALITY_MAX_ENTRIES = 200


@dataclass
class RecallQualityRecord:
    """Per-recall quality record for governance and diagnostics.

    Tracks what was queried, how many results were returned, the average
    similarity/confidence of results, and which layers contributed.
    """
    timestamp: float
    query: str
    layer: str
    limit: int
    total_results: int
    avg_similarity: float
    avg_confidence: float
    result_ids: list[int] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query[:200],
            "layer": self.layer,
            "limit": self.limit,
            "total_results": self.total_results,
            "avg_similarity": self.avg_similarity,
            "avg_confidence": self.avg_confidence,
            "result_ids": self.result_ids[:20],
            "source_types": self.source_types[:20],
            "duration_ms": round(self.duration_ms, 1),
        }


async def _append_recall_quality(
    db: AsyncSession, owner_id: int, conversation_id: int | None, record: RecallQualityRecord,
) -> None:
    d = record.to_dict()
    db.add(RecallQualityModel(
        owner_id=owner_id,
        conversation_id=conversation_id,
        query=d["query"],
        layer=d["layer"],
        limit_val=d["limit"],
        total_results=d["total_results"],
        avg_similarity=d["avg_similarity"],
        avg_confidence=d["avg_confidence"],
        result_ids=d["result_ids"],
        source_types=d["source_types"],
        duration_ms=d["duration_ms"],
    ))
    await db.commit()


async def record_recall_quality(
    owner_id: int, conversation_id: int | None, record: RecallQualityRecord,
) -> None:
    """Record a recall quality metric for governance (persisted via DB).

    Opens its own DB session (fire-and-forget quality metric).
    """
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await _append_recall_quality(db, owner_id, conversation_id, record)


async def get_recall_quality_summary(
    db: AsyncSession, owner_id: int | None = None,
) -> dict:
    """Aggregate recall quality metrics for governance dashboard.

    Reads from DB (cross-worker safe).
    Returns dict with keys:
        total_recalls, per_layer stats, avg_hit_rate, avg_noise_estimate
    """
    q = select(RecallQualityModel)
    if owner_id is not None and owner_id > 0:
        q = q.where(RecallQualityModel.owner_id == owner_id)
    q = q.order_by(desc(RecallQualityModel.created_at)).limit(_RECALL_QUALITY_MAX_ENTRIES)
    r = await db.execute(q)
    history = [
        {
            "layer": row.layer,
            "total_results": row.total_results,
            "avg_similarity": row.avg_similarity,
            "avg_confidence": row.avg_confidence,
        }
        for row in r.scalars().all()
    ]

    if not history:
        return {
            "total_recalls": 0,
            "per_layer": {},
            "avg_hit_rate": 0,
            "avg_noise_estimate": 0,
            "credibility_score": 0,
        }

    total = len(history)
    layers: dict[str, list[dict]] = {}
    for rec in history:
        layers.setdefault(rec["layer"], []).append(rec)

    per_layer = {}
    for layer_name, recs in layers.items():
        avg_sim = sum(r.get("avg_similarity", 0) for r in recs) / len(recs) if recs else 0
        avg_conf = sum(r.get("avg_confidence", 0) for r in recs) / len(recs) if recs else 0
        hit_rate = sum(1 for r in recs if r.get("total_results", 0) > 0) / len(recs) if recs else 0
        per_layer[layer_name] = {
            "total_recalls": len(recs),
            "avg_similarity": round(avg_sim, 3),
            "avg_confidence": round(avg_conf, 3),
            "hit_rate": round(hit_rate, 3),
            "avg_results": round(sum(r.get("total_results", 0) for r in recs) / len(recs), 1) if recs else 0,
        }

    overall_hit = sum(1 for r in history if r.get("total_results", 0) > 0) / total if total else 0
    low_conf_count = sum(
        1 for r in history if r.get("avg_similarity", 0) > 0 and r.get("avg_similarity", 0) < 0.5
    )
    noise_est = low_conf_count / total if total else 0
    avg_overall_sim = sum(r.get("avg_similarity", 0) for r in history) / total if total else 0
    credibility = round((overall_hit * 0.4 + avg_overall_sim * 0.6) * 100, 1)

    return {
        "total_recalls": total,
        "per_layer": per_layer,
        "avg_hit_rate": round(overall_hit, 3),
        "avg_noise_estimate": round(noise_est, 3),
        "credibility_score": credibility,
    }

# ── Static file memory (Layer 0) ───────────────────────────────────────────
# Zero-latency deterministic memory injected every turn.
# Files in data/static-memory/ are read and cached at assembly time.


STATIC_MEMORY_DIR = "data/static-memory"
_STATIC_MEMORY_CACHE: dict[str, tuple[float, list[str], dict[str, float]]] = {}
_STATIC_MEMORY_CACHE_TTL = 300.0  # 5 minutes (fallback if mtime is unsupported)


def invalidate_static_memory_cache() -> None:
    """Force re-read on next access."""
    global _STATIC_MEMORY_CACHE  # noqa: PLW0603
    _STATIC_MEMORY_CACHE = {}


def _check_cache_mtime(cached_mtimes: dict[str, float]) -> bool:
    """Check if any cached file's mtime has changed. Returns True if cache is still valid."""
    for fpath, cached_mtime in cached_mtimes.items():
        try:
            current_mtime = os.path.getmtime(fpath)
        except OSError:
            return False
        if current_mtime != cached_mtime:
            return False
    return True


def read_static_memory_files(base_dir: str | None = None) -> list[str]:
    """Read all markdown files from the static memory directory.

    Returns a list of content strings, one per file.  Files are sorted by
    name for deterministic ordering.  Cache is valid for ``_STATIC_MEMORY_CACHE_TTL``
    seconds, and additionally validates file mtime on each access so that
    content changes (without path changes) are detected immediately.

    This is Layer 0 of the memory system — no DB, no embedding, no network.
    Pure file read, pure string injection.
    """
    global _STATIC_MEMORY_CACHE  # noqa: PLW0603
    import time
    resolve_dir = base_dir or STATIC_MEMORY_DIR
    cache_key = resolve_dir

    now = time.time()
    cached = _STATIC_MEMORY_CACHE.get(cache_key)
    if cached is not None:
        loaded_at, contents, file_mtimes = cached
        ttl_valid = (now - loaded_at) < _STATIC_MEMORY_CACHE_TTL
        mtime_valid = _check_cache_mtime(file_mtimes)
        if ttl_valid and mtime_valid:
            logger.debug("Static memory cache HIT: TTL+mtime valid for %s (%d files, %.1fs old)",
                         resolve_dir, len(file_mtimes), now - loaded_at)
            return list(contents)
        if not mtime_valid:
            logger.debug("Static memory cache invalidated by mtime change for %s", resolve_dir)
        else:
            logger.debug("Static memory cache expired (TTL) for %s, re-reading", resolve_dir)

    dir_path = Path(resolve_dir)
    if not dir_path.is_dir():
        _STATIC_MEMORY_CACHE[cache_key] = (now, [], {})
        return []

    contents: list[str] = []
    file_mtimes: dict[str, float] = {}
    try:
        md_files = sorted(dir_path.glob("*.md"))
    except (PermissionError, OSError) as exc:
        logger.warning("Failed to list static memory directory %s: %s", resolve_dir, exc)
        _STATIC_MEMORY_CACHE[cache_key] = (now, [], {})
        return []
    for md_path in md_files:
        try:
            text = md_path.read_text(encoding="utf-8")
            if text.strip():
                contents.append(text.strip())
            file_mtimes[str(md_path)] = md_path.stat().st_mtime
        except Exception as exc:
            logger.warning("Failed to read static memory file %s: %s", md_path, exc)

    _STATIC_MEMORY_CACHE[cache_key] = (now, contents, file_mtimes)
    logger.debug("Static memory cache LOADED %d files from %s", len(contents), resolve_dir)
    return contents


def format_static_memory_for_injection(texts: list[str]) -> str:
    """Format static memory texts into a structured prompt injection block."""
    if not texts:
        return ""
    blocks = []
    for t in texts:
        blocks.append(f"  <rule>\n{t}\n  </rule>")
    return "\n<static_memory>\n" + "\n".join(blocks) + "\n</static_memory>"


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
            caller=f"user:{owner_id}",
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
    _t0 = time.time()
    try:
        result = await call_capability(
            "memory", "recall",
            {
                "query": query,
                "limit": limit,
                "expand_chain": expand_chain,
            },
            caller=f"user:{owner_id}",
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            items = result["data"]
            _t1 = time.time()
            sims = [r.get("similarity", 0) or 0 for r in items]
            confs = [r.get("confidence", 0) or 0 for r in items]
            record_recall_quality(RecallQualityRecord(
                timestamp=_t0, query=query[:100],
                layer="semantic", limit=limit,
                total_results=len(items),
                avg_similarity=sum(sims) / len(sims) if sims else 0,
                avg_confidence=sum(confs) / len(confs) if confs else 0,
                result_ids=[r.get("id", 0) for r in items[:20]],
                source_types=[r.get("memory_type", "semantic") for r in items[:20]],
                duration_ms=(_t1 - _t0) * 1000,
            ))
            return items
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
            caller=f"user:{owner_id}",
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
            caller=f"user:{owner_id}",
            caller_role="admin",
        )
        return result if result else {}
    except Exception as e:
        logger.warning("触发dream failed (non-fatal): %s", e)
        return {}


# ── Three-layer memory helpers ──────────────────────────────────────────


async def recall_stable_rules(
    owner_id: int,
    rule_types: list[str] | None = None,
) -> list[dict]:
    """Recall stable rule memories (project boundaries, user preferences, hard constraints).

    Args:
        owner_id: The user whose stable rules to fetch.
        rule_types: Optional filter — only return rules of these types (e.g.
            ``["project_boundary", "user_preference"]``). ``None`` means all types.

    Returns:
        List of rule dicts. Each item contains at least ``id``, ``rule_type``,
        ``content``, ``priority``. Falls back to ``[]`` on failure.
    """
    _t0 = time.time()
    try:
        result = await call_capability(
            "memory", "recall_stable_rules",
            {"rule_types": rule_types or []},
            caller=f"user:{owner_id}",
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            items = result["data"]
            _t1 = time.time()
            confs = [r.get("priority", 0) / 100 for r in items if r.get("priority")]
            record_recall_quality(RecallQualityRecord(
                timestamp=_t0, query=f"stable_rules:{rule_types or 'all'}",
                layer="stable_rules", limit=100,
                total_results=len(items),
                avg_similarity=sum(confs) / len(confs) if confs else 0,
                avg_confidence=sum(confs) / len(confs) if confs else 0,
                result_ids=[r.get("id", 0) for r in items[:20]],
                source_types=["stable_rule"] * len(items),
                duration_ms=(_t1 - _t0) * 1000,
            ))
            return items
        return []
    except Exception as e:
        logger.warning("recall_stable_rules failed (non-fatal): %s", e)
        return []


async def recall_chunk(
    owner_id: int,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Recall chunk-level memories with provenance.

    Chunks are paragraph-sized memory units that carry a ``provenance`` field
    (e.g. source file, conversation reference) so the agent can cite its origin.

    Args:
        owner_id: The user whose chunks to search.
        query: Natural-language query for semantic chunk search.
        limit: Max number of chunks to return.

    Returns:
        List of chunk dicts. Each item contains at least ``id``, ``text``,
        ``provenance``, ``similarity``. Falls back to ``[]`` on failure.
    """
    _t0 = time.time()
    try:
        result = await call_capability(
            "memory", "recall_chunk",
            {"query": query, "limit": limit},
            caller=f"user:{owner_id}",
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            items = result["data"]
            _t1 = time.time()
            sims = [r.get("similarity", 0) or 0 for r in items]
            confs = [r.get("confidence", 0) or 0 for r in items]
            record_recall_quality(RecallQualityRecord(
                timestamp=_t0, query=query[:100],
                layer="chunk", limit=limit,
                total_results=len(items),
                avg_similarity=sum(sims) / len(sims) if sims else 0,
                avg_confidence=sum(confs) / len(confs) if confs else 0,
                result_ids=[r.get("id", 0) for r in items[:20]],
                source_types=[r.get("provenance", "chunk")[:50] for r in items[:20]],
                duration_ms=(_t1 - _t0) * 1000,
            ))
            return items
        return []
    except Exception as e:
        logger.warning("recall_chunk failed (non-fatal): %s", e)
        return []


async def save_stable_rule(
    owner_id: int,
    rule_type: str,
    content: str,
    priority: int = 0,
    source: str | None = None,
) -> dict:
    """Save a stable rule to the memory module.

    Stable rules outlive conversations — they encode project boundaries,
    user preferences, and hard constraints the agent must always follow.

    Args:
        owner_id: The user this rule belongs to.
        rule_type: Category of the rule (e.g. ``"project_boundary"``,
            ``"user_preference"``, ``"hard_constraint"``).
        content: The rule text.
        priority: Numeric priority (higher = more important). Default 0.
        source: Optional identifier of what created this rule.

    Returns:
        Capability response dict with ``success`` and ``data`` (containing
        the new rule ``id``). Falls back to an error dict on failure.
    """
    try:
        result = await call_capability(
            "memory", "save_stable_rule",
            {
                "rule_type": rule_type,
                "content": content,
                "priority": priority,
                "source": source,
            },
            caller=f"user:{owner_id}",
            caller_role="admin",
        )
        return result
    except Exception as e:
        logger.warning("save_stable_rule failed (non-fatal): %s", e)
        return {"success": False, "error": str(e), "fallback": True}


async def three_layer_recall(
    owner_id: int,
    query: str,
) -> dict[str, Any]:
    """Combined recall from all three memory layers in one call.

    Gathers stable rules (all active), chunk-level results, and semantic
    recall results, then assembles a formatted prompt injection string.

    All three layers are fetched concurrently.  A failure in any single
    layer does not affect the other layers.

    Args:
        owner_id: The user to recall for.
        query: Natural-language query driving semantic searches (chunks + semantic).

    Returns:
        Dict with keys:
            ``stable_rules`` — all active stable rules for this user
            ``chunks``       — chunk-level recall results
            ``semantic``     — existing semantic recall results
            ``injection``    — formatted prompt injection string combining all three layers
    """
    import asyncio

    async def _safe_stable():
        try:
            return await recall_stable_rules(owner_id)
        except Exception as e:
            logger.warning("three_layer_recall » stable_rules failed: %s", e)
            return []

    async def _safe_chunk():
        try:
            return await recall_chunk(owner_id, query)
        except Exception as e:
            logger.warning("three_layer_recall » recall_chunk failed: %s", e)
            return []

    async def _safe_semantic():
        try:
            return await recall(owner_id, query)
        except Exception as e:
            logger.warning("three_layer_recall » semantic recall failed: %s", e)
            return []

    stable_rules, chunks, semantic = await asyncio.gather(
        _safe_stable(), _safe_chunk(), _safe_semantic(),
    )

    injection = _format_three_layer_injection(stable_rules, chunks, semantic)

    return {
        "stable_rules": stable_rules,
        "chunks": chunks,
        "semantic": semantic,
        "injection": injection,
    }


def _format_three_layer_injection(
    rules: list[dict],
    chunks: list[dict],
    semantic: list[dict],
) -> str:
    """Format the three memory layers into a single structured prompt injection string.

    The output is designed to be prepended to the system prompt so the LLM
    sees all relevant context organised by memory tier.
    """
    parts: list[str] = []

    # ── Layer 1: Stable rules ────────────────────────────────────────
    if rules:
        rules_sorted = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
        rule_lines: list[str] = []
        for r in rules_sorted:
            rule_type = r.get("rule_type", "general")
            content = r.get("content", "")
            rule_lines.append(f"  [{rule_type}] {content}")
        parts.append("<stable_rules>\n" + "\n".join(rule_lines) + "\n</stable_rules>")

    # ── Layer 2: Chunks ──────────────────────────────────────────────
    if chunks:
        chunk_lines: list[str] = []
        for i, c in enumerate(chunks, 1):
            text = c.get("text", "")
            provenance = c.get("provenance", "")
            if provenance:
                chunk_lines.append(f"  [{i}] {text}  (source: {provenance})")
            else:
                chunk_lines.append(f"  [{i}] {text}")
        parts.append("<chunks>\n" + "\n".join(chunk_lines) + "\n</chunks>")

    # ── Layer 3: Semantic ────────────────────────────────────────────
    if semantic:
        sem_lines: list[str] = []
        for i, s in enumerate(semantic, 1):
            text = s.get("text") or s.get("summary", "")
            similarity = s.get("similarity", "")
            if similarity:
                sem_lines.append(f"  [{i}] {text}  (relevance: {similarity})")
            else:
                sem_lines.append(f"  [{i}] {text}")
        parts.append("<semantic_memories>\n" + "\n".join(sem_lines) + "\n</semantic_memories>")

    return "\n\n".join(parts)
