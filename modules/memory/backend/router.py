import json
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, or_, func, and_, text, Float as SAFloat, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.services.module_registry import register_capability
from app.services.task_worker import register_task_handler

logger = logging.getLogger("v2.memory").getChild("router")

from huashiwangzu_modules.memory.models import MemoryRecord, MemoryLink, MemoryExperience
from huashiwangzu_modules.memory.init_db import run_init

router = APIRouter(prefix="/api/memory", tags=["memory"])

# ── Config ──────────────────────────────────────────────────────
MEMORY_CHEAP_MODEL_KEY = "deepseek-v4-flash"
MEMORY_TOP_K_DEFAULT = 5
MEMORY_RECALL_CANDIDATES = 20
MEMORY_SIMILARITY_THRESHOLD = 0.3
MEMORY_CHAIN_EXPAND_THRESHOLD = 0.4
MEMORY_CHAIN_MAX_EXPANSION = 3
MEMORY_DREAM_DECAY_DAYS = 30
MEMORY_DREAM_SIMILARITY_MERGE = 0.92


class SaveMemoryRequest(BaseModel):
    text: str
    tags: str | None = None
    source: str | None = None
    conversation_id: int | None = None


class RecallRequest(BaseModel):
    query: str
    limit: int = 5
    expand_chain: bool = False


class DeleteMemoryRequest(BaseModel):
    id: int


class FuseRequest(BaseModel):
    query: str
    ids: list[int]


class RethinkRequest(BaseModel):
    id: int
    text: str
    tags: str | None = None


class ReplaceRequest(BaseModel):
    id: int
    old_text: str
    new_text: str


class InsertRequest(BaseModel):
    id: int
    text: str


# ── Helpers ─────────────────────────────────────────────────────

async def _ensure_init() -> None:
    await run_init()


def _parse_user_id(caller: str) -> int:
    if caller and caller.startswith("user:"):
        return int(caller.split(":", 1)[1])
    return 0


async def _call_cheap_model(messages: list[dict]) -> str:
    """调用便宜模型（models.json 配置），返回 content 文本。失败返回空字符串。"""
    try:
        from app.gateway.router import gateway_router
        result = await gateway_router.chat(messages=messages, profile_key=MEMORY_CHEAP_MODEL_KEY)
        return result.get("content", "") or ""
    except Exception as e:
        logger.warning("Cheap model call failed: %s", e)
        return ""


async def _compute_embedding(text: str) -> list[float] | None:
    """Compute embedding via framework model_services. Returns None on failure."""
    try:
        from app.services.model_services import get_embedding
        return await get_embedding(text[:2048])
    except Exception as e:
        logger.warning("Embedding computation failed: %s", e)
        return None


async def _distill_summary(text: str, source: str | None = None) -> dict:
    """Use cheap LLM to distill a memory into summary + structured fields.
    Returns {summary, memory_type, keywords} or empty dict on failure."""
    src_hint = f"（来源：{source}）" if source else ""
    prompt = (
        "你是一个记忆摘要助手。分析以下记忆内容，提取关键信息。\n\n"
        f"记忆内容：{text[:1500]}{src_hint}\n\n"
        "请输出 JSON（不要额外文字）：\n"
        "{\n"
        '  "summary": "一句话摘要（≤50字）",\n'
        '  "memory_type": "事实/fact | 偏好/preference | 约定/convention | 其他/other",\n'
        '  "keywords": "关键词1,关键词2,关键词3"\n'
        "}"
    )
    content = await _call_cheap_model([
        {"role": "system", "content": "你是一个精确的记忆摘要工具，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ])
    if not content:
        return {}
    try:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            cleaned = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(cleaned).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(content[start:end + 1])
            return {
                "summary": str(data.get("summary", ""))[:200],
                "memory_type": str(data.get("memory_type", "other"))[:32],
                "keywords": str(data.get("keywords", ""))[:500],
            }
    except Exception as e:
        logger.warning("Distill JSON parse failed: %s", e)
    return {}


async def _hybrid_recall(
    db: AsyncSession,
    owner_id: int,
    query: str,
    top_k: int = 5,
    expand_chain: bool = False,
) -> list[dict]:
    """Hybrid recall: vector cosine → rerank → fallback keyword → chain expand.
    Returns list of {id, text, summary, tags, confidence, recency_score,
    memory_type, keywords, raw_id, similarity, created_at}."""
    query_vec = await _compute_embedding(query)
    use_vector = query_vec is not None and len(query) > 3

    if use_vector:
        try:
            vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
            sql = text(f"""
                SELECT id, owner_id, text, summary, tags, confidence,
                       recency_score, raw_id, conversation_id, source,
                       memory_type, keywords, access_count, created_at,
                       (1 - (embedding <=> '{vec_literal}'::vector)) AS similarity
                FROM memory_records
                WHERE owner_id = :owner_id
                  AND embedding IS NOT NULL
                  AND (1 - (embedding <=> '{vec_literal}'::vector)) >= :threshold
                ORDER BY similarity DESC
                LIMIT :candidates
            """)
            r = await db.execute(sql, {
                "owner_id": owner_id,
                "threshold": MEMORY_SIMILARITY_THRESHOLD,
                "candidates": MEMORY_RECALL_CANDIDATES,
            })
            rows = r.mappings().all()
        except Exception as e:
            logger.warning("Vector recall failed, fallback to keyword: %s", e)
            rows = []
    else:
        rows = []

    if not rows:
        keyword = f"%{query}%"
        stmt = (
            select(MemoryRecord)
            .where(
                MemoryRecord.owner_id == owner_id,
                or_(
                    MemoryRecord.text.ilike(keyword),
                    MemoryRecord.tags.ilike(keyword),
                    MemoryRecord.summary.ilike(keyword),
                    MemoryRecord.keywords.ilike(keyword),
                ),
            )
            .order_by(MemoryRecord.confidence.desc(), MemoryRecord.recency_score.desc())
            .limit(top_k)
        )
        r = await db.execute(stmt)
        items = r.scalars().all()
        results = [_memory_to_dict(m, similarity=0.0) for m in items]
        # Track access count
        for m in items:
            await db.execute(
                text("UPDATE memory_records SET access_count = access_count + 1 WHERE id = :id"),
                {"id": m.id},
            )
        await db.commit()
        if expand_chain and results:
            results = await _expand_via_chain(db, owner_id, results, top_k)
        return results

    # Rerank via framework
    try:
        from app.services.model_services import rerank
        documents = [r["summary"] or r["text"][:200] for r in rows]
        reranked = await rerank(query, documents, top_k=top_k)
        reranked_ids = {r["index"]: r["relevance_score"] for r in reranked}
        results = []
        for idx, row in enumerate(rows):
            row = dict(row)
            row["rerank_score"] = reranked_ids.get(idx)
            results.append(row)
        results.sort(key=lambda r: r["rerank_score"] or 0, reverse=True)
    except Exception as e:
        logger.warning("Rerank failed, using raw vector scores: %s", e)
        results = [dict(r) for r in rows]
        results.sort(key=lambda r: r["similarity"], reverse=True)

    results = results[:top_k]
    # Cast dates to isoformat
    for r in results:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()

    # Track access
    ids = [r["id"] for r in results]
    for rid in ids:
        await db.execute(
            text("UPDATE memory_records SET access_count = access_count + 1 WHERE id = :id"),
            {"id": rid},
        )
    await db.commit()

    if expand_chain and results:
        results = await _expand_via_chain(db, owner_id, results, top_k)
    return results


async def _expand_via_chain(
    db: AsyncSession, owner_id: int, results: list[dict], top_k: int,
) -> list[dict]:
    """顺链扩展：从种子记忆沿高权 memory_links 带出 1 跳相关记忆。"""
    seed_ids = [r["id"] for r in results]
    seen = set(seed_ids)
    stmt = (
        select(MemoryLink, MemoryRecord)
        .join(MemoryRecord, and_(
            MemoryRecord.id == MemoryLink.to_id,
            MemoryRecord.owner_id == owner_id,
        ))
        .where(
            MemoryLink.from_id.in_(seed_ids),
            MemoryLink.weight >= MEMORY_CHAIN_EXPAND_THRESHOLD,
        )
        .order_by(MemoryLink.weight.desc())
        .limit(MEMORY_CHAIN_MAX_EXPANSION)
    )
    r = await db.execute(stmt)
    expanded = []
    for link, mem in r.unique().all():
        if mem.id in seen:
            continue
        seen.add(mem.id)
        expanded.append(_memory_to_dict(mem, similarity=link.weight))
    return results + expanded


def _memory_to_dict(m, similarity: float = 0.0) -> dict:
    return {
        "id": m.id,
        "text": m.text,
        "summary": m.summary,
        "tags": m.tags,
        "confidence": m.confidence,
        "recency_score": m.recency_score,
        "raw_id": m.raw_id,
        "memory_type": m.memory_type,
        "keywords": m.keywords,
        "source": m.source,
        "conversation_id": m.conversation_id,
        "similarity": similarity,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── HTTP Endpoints ──────────────────────────────────────────────

@router.post("/save")
async def http_save(
    req: SaveMemoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    if not req.text.strip():
        raise ValidationError("内容不能为空")
    # Save raw text (原始层)
    memory = MemoryRecord(
        owner_id=current_user.id,
        text=req.text,
        tags=req.tags if req.tags else None,
        source=req.source or "user-save",
        conversation_id=req.conversation_id,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    # Embedding synchronously (fast)
    await _update_embedding(memory.id, req.text)
    # Distillation async (cheap LLM may take time)
    await _enqueue_post_save(memory.id, req.text, req.source)
    return ApiResponse(data={"id": memory.id, "status": "saved"})


async def _post_save_process(memory_id: int, content: str, source: str | None) -> None:
    """Post-save: compute embedding + distill summary. Non-blocking."""
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            mem = await db.get(MemoryRecord, memory_id)
            if not mem:
                return
            # Compute embedding
            vec = await _compute_embedding(content)
            if vec:
                vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
                sql = f"UPDATE memory_records SET embedding = '{vec_literal}'::vector WHERE id = :id"
                await db.execute(text(sql), {"id": memory_id})
            # Distill summary (cheap model)
            distilled = await _distill_summary(content, source)
            update_parts = []
            params = {"id": memory_id}
            if distilled.get("summary"):
                update_parts.append("summary = :summary")
                params["summary"] = distilled["summary"]
            if distilled.get("memory_type"):
                update_parts.append("memory_type = :memory_type")
                params["memory_type"] = distilled["memory_type"]
            if distilled.get("keywords"):
                update_parts.append("keywords = :keywords")
                params["keywords"] = distilled["keywords"]
            if update_parts:
                sql = "UPDATE memory_records SET " + ", ".join(update_parts) + " WHERE id = :id"
                await db.execute(text(sql), params)
            await db.commit()
    except Exception as e:
        logger.warning("Post-save processing failed (non-fatal): %s", e)


async def _update_embedding(memory_id: int, content: str) -> bool:
    """Compute and save embedding synchronously (used in save endpoint)."""
    try:
        from app.database import AsyncSessionLocal
        vec = await _compute_embedding(content)
        if vec:
            async with AsyncSessionLocal() as db:
                vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
                sql = f"UPDATE memory_records SET embedding = '{vec_literal}'::vector WHERE id = :id"
                await db.execute(text(sql), {"id": memory_id})
                await db.commit()
            return True
    except Exception as e:
        logger.warning("Embedding update failed: %s", e)
    return False


@router.post("/recall")
async def http_recall(
    req: RecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    results = await _hybrid_recall(db, current_user.id, req.query, req.limit, req.expand_chain)
    return ApiResponse(data=results)


@router.get("/list")
async def http_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
    limit: int = 50,
    offset: int = 0,
):
    await _ensure_init()
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.owner_id == current_user.id)
        .order_by(MemoryRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    r = await db.execute(stmt)
    items = r.scalars().all()
    return ApiResponse(data=[_memory_to_dict(m) for m in items])


@router.post("/delete")
async def http_delete(
    req: DeleteMemoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能删除自己的记忆")
    # Cascade delete links
    await db.execute(
        text("DELETE FROM memory_links WHERE from_id = :id OR to_id = :id"),
        {"id": req.id},
    )
    await db.delete(memory)
    await db.commit()
    return ApiResponse(data={"id": req.id, "status": "deleted"})


@router.post("/fuse")
async def http_fuse(
    req: FuseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    if not req.ids:
        raise ValidationError("ids 不能为空")
    result = await _do_fuse(db, current_user.id, req.query, req.ids)
    return ApiResponse(data=result)


@router.post("/rethink")
async def http_rethink(
    req: RethinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    old_text = memory.text
    memory.text = req.text
    if req.tags is not None:
        memory.tags = req.tags
    memory.source = "rethink"
    await db.commit()
    # Recompute embedding + summary
    await _enqueue_post_save(memory.id, req.text, "rethink")
    return ApiResponse(data={"id": memory.id, "status": "rethought", "old_text": old_text})


@router.post("/replace")
async def http_replace(
    req: ReplaceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    if req.old_text not in memory.text:
        raise ValidationError("未找到要替换的文本")
    memory.text = memory.text.replace(req.old_text, req.new_text, 1)
    memory.source = "edit"
    await db.commit()
    await _enqueue_post_save(memory.id, memory.text, "edit")
    return ApiResponse(data={"id": memory.id, "status": "replaced"})


@router.post("/insert")
async def http_insert(
    req: InsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await _ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    memory.text += "\n" + req.text
    memory.source = "edit"
    await db.commit()
    await _enqueue_post_save(memory.id, memory.text, "edit")
    return ApiResponse(data={"id": memory.id, "status": "inserted"})


@router.post("/dream")
async def http_dream(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    """手动触发 dream 自优化（管理员可调）。"""
    await _ensure_init()
    result = await _do_dream(db, current_user.id)
    return ApiResponse(data=result)


# ── Core Logic ──────────────────────────────────────────────────

async def _do_fuse(db: AsyncSession, owner_id: int, query: str, ids: list[int]) -> dict:
    """On-demand fusion: merge multiple memories into a query-tailored brief."""
    memories = []
    for mid in ids:
        m = await db.get(MemoryRecord, mid)
        if m and m.owner_id == owner_id:
            memories.append(m)
    if not memories:
        return {"fused": "", "source_ids": [], "note": "无有效记忆"}
    # Build a consolidated text
    parts = []
    for i, m in enumerate(memories):
        label = m.summary or m.text[:100]
        parts.append(f"[{i+1}] {label}\n完整：{m.text[:500]}")
    combined = "\n\n".join(parts)
    prompt = (
        f"用户查询：{query}\n\n"
        f"相关记忆：\n{combined}\n\n"
        "请根据用户查询，将以上记忆融合成一段贴合查询的简报。"
        "要求：简洁、贴题、保留关键信息。直接输出融合后的文本，不要额外格式。"
    )
    content = await _call_cheap_model([
        {"role": "system", "content": "你是一个记忆融合助手，擅长将多条相关信息融合成贴合查询的简报。"},
        {"role": "user", "content": prompt},
    ])
    return {
        "fused": content or combined[:1000],
        "source_ids": [m.id for m in memories],
        "note": "融合成功" if content else "融合失败，降级为拼接摘要",
    }


async def _do_dream(db: AsyncSession, owner_id: int) -> dict:
    """Dream self-optimization: merge duplicates + build links + decay old memories."""
    report = {"merged": 0, "links_created": 0, "decayed": 0}

    # 1. Merge duplicates: find high-similarity pairs using pgvector cosine
    # Use raw SQL with vector distance for efficient comparison
    try:
        merge_sql = text("""
            SELECT a.id AS keep_id, b.id AS drop_id,
                   (1 - (a.embedding <=> b.embedding)) AS similarity
            FROM memory_records a
            JOIN memory_records b ON a.owner_id = b.owner_id AND a.id < b.id
            WHERE a.owner_id = :owner_id
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
              AND (1 - (a.embedding <=> b.embedding)) >= :threshold
            ORDER BY similarity DESC
        """)
        merge_candidates = await db.execute(merge_sql, {
            "owner_id": owner_id,
            "threshold": MEMORY_DREAM_SIMILARITY_MERGE,
        })
        merge_rows = merge_candidates.mappings().all()
        dropped = set()
        for row in merge_rows:
            keep_id = row["keep_id"]
            drop_id = row["drop_id"]
            if keep_id in dropped or drop_id in dropped:
                continue
            # Merge: keep higher confidence
            keep = await db.get(MemoryRecord, keep_id)
            drop = await db.get(MemoryRecord, drop_id)
            if not keep or not drop:
                continue
            new_conf = max(keep.confidence, drop.confidence)
            keep.confidence = new_conf
            keep.access_count = (keep.access_count or 0) + (drop.access_count or 0)
            # Delete links to/from drop_id
            await db.execute(
                text("DELETE FROM memory_links WHERE from_id = :id OR to_id = :id"),
                {"id": drop_id},
            )
            await db.delete(drop)
            dropped.add(drop_id)
            report["merged"] += 1
    except Exception as e:
        logger.warning("Dream merge failed: %s", e)

    # 2. Build links: find semantically similar pairs using pgvector
    try:
        link_sql = text("""
            SELECT a.id AS from_id, b.id AS to_id,
                   (1 - (a.embedding <=> b.embedding)) AS similarity
            FROM memory_records a
            JOIN memory_records b ON a.owner_id = b.owner_id AND a.id < b.id
            WHERE a.owner_id = :owner_id
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
              AND (1 - (a.embedding <=> b.embedding)) >= :threshold
              AND NOT EXISTS (
                  SELECT 1 FROM memory_links
                  WHERE (from_id = a.id AND to_id = b.id)
                     OR (from_id = b.id AND to_id = a.id)
              )
            ORDER BY similarity DESC
        """)
        link_candidates = await db.execute(link_sql, {
            "owner_id": owner_id,
            "threshold": 0.55,
        })
        for row in link_candidates.mappings().all():
            link = MemoryLink(
                from_id=row["from_id"],
                to_id=row["to_id"],
                relation="semantic_related",
                weight=row["similarity"],
                owner_id=owner_id,
            )
            db.add(link)
            report["links_created"] += 1
    except Exception as e:
        logger.warning("Dream link creation failed: %s", e)

    # 3. Decay old memories by recency and access count
    try:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=MEMORY_DREAM_DECAY_DAYS)
        decay_result = await db.execute(
            text("""
                UPDATE memory_records
                SET recency_score = GREATEST(recency_score * 0.85, 0.1)
                WHERE owner_id = :owner_id
                  AND updated_at < :cutoff
                  AND access_count < 3
            """),
            {"owner_id": owner_id, "cutoff": cutoff},
        )
        report["decayed"] = decay_result.rowcount
    except Exception as e:
        logger.warning("Dream decay failed: %s", e)

    await db.commit()
    return report


# ── Experience: 经验能力（批3） ────────────────────────────────

EXPERIENCE_SIMILARITY_THRESHOLD = 0.3
EXPERIENCE_DEDUP_THRESHOLD = 0.85
EXPERIENCE_FAIL_PENALTY = 2


async def _experience_to_dict(exp) -> dict:
    """Convert experience ORM row to dict."""
    return {
        "id": exp.id,
        "trigger_condition": exp.trigger_condition,
        "steps": exp.steps,
        "tools_used": exp.tools_used,
        "success_weight": exp.success_weight,
        "fail_count": exp.fail_count,
        "fail_notes": exp.fail_notes,
        "source_conversation_id": exp.source_conversation_id,
        "active": exp.active,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "updated_at": exp.updated_at.isoformat() if exp.updated_at else None,
    }


async def _save_experience(
    db: AsyncSession,
    trigger_condition: str,
    steps: str,
    tools_used: str | None = None,
    source_conversation_id: int | None = None,
) -> dict:
    """Save a success experience with dedup. If semantically similar exists, increment weight."""
    # 容错：steps/tools_used 常以结构化 list/dict 传入，统一序列化成 JSON 字符串再存 TEXT 列
    if isinstance(steps, (list, dict)):
        steps = json.dumps(steps, ensure_ascii=False)
    if isinstance(tools_used, (list, dict)):
        tools_used = json.dumps(tools_used, ensure_ascii=False)
    if not (trigger_condition or "").strip() or not (steps or "").strip():
        raise ValidationError("trigger_condition and steps required")

    trigger_vec = await _compute_embedding(trigger_condition)

    # Dedup: check semantically similar active experiences
    if trigger_vec:
        try:
            vec_literal = "[" + ",".join(str(v) for v in trigger_vec) + "]"
            sql = text(f"""
                SELECT id, trigger_condition, steps, success_weight
                FROM memory_experiences
                WHERE active = true
                  AND trigger_embedding IS NOT NULL
                  AND (1 - (trigger_embedding <=> '{vec_literal}'::vector)) >= :threshold
                ORDER BY (1 - (trigger_embedding <=> '{vec_literal}'::vector)) DESC
                LIMIT 3
            """)
            r = await db.execute(sql, {"threshold": EXPERIENCE_DEDUP_THRESHOLD})
            candidates = r.mappings().all()
        except Exception as e:
            logger.warning("Experience dedup vector search failed: %s", e)
            candidates = []

        for cand in candidates:
            try:
                existing_steps = json.loads(cand["steps"]) if isinstance(cand["steps"], str) else cand["steps"]
                new_steps = json.loads(steps) if isinstance(steps, str) else steps
                if isinstance(existing_steps, list) and isinstance(new_steps, list):
                    same_tools = len(existing_steps) == len(new_steps)
            except (json.JSONDecodeError, TypeError):
                same_tools = False
            if same_tools:
                # Dedup: increment weight of existing
                await db.execute(
                    text("UPDATE memory_experiences SET success_weight = success_weight + 1, updated_at = NOW() WHERE id = :id"),
                    {"id": cand["id"]},
                )
                await db.commit()
                return {"id": cand["id"], "deduplicated": True, "success_weight": (cand["success_weight"] or 1) + 1}

    # New experience
    exp = MemoryExperience(
        trigger_condition=trigger_condition,
        trigger_embedding=trigger_vec,
        steps=steps,
        tools_used=tools_used,
        source_conversation_id=source_conversation_id,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return {"id": exp.id, "deduplicated": False, "success_weight": 1}


async def _match_experience(
    db: AsyncSession,
    query: str,
    limit: int = 2,
) -> list[dict]:
    """Semantic match experiences by query. Returns top active experiences sorted by net weight."""
    query_vec = await _compute_embedding(query)
    if query_vec:
        try:
            vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
            sql = text(f"""
                SELECT id, trigger_condition, steps, tools_used,
                       success_weight, fail_count, fail_notes,
                       source_conversation_id, created_at, updated_at,
                       (1 - (trigger_embedding <=> '{vec_literal}'::vector)) AS similarity
                FROM memory_experiences
                WHERE active = true
                  AND trigger_embedding IS NOT NULL
                  AND (1 - (trigger_embedding <=> '{vec_literal}'::vector)) >= :threshold
                ORDER BY (success_weight - fail_count * :penalty) DESC,
                         similarity DESC
                LIMIT :limit
            """)
            r = await db.execute(sql, {
                "threshold": EXPERIENCE_SIMILARITY_THRESHOLD,
                "penalty": EXPERIENCE_FAIL_PENALTY,
                "limit": limit,
            })
            rows = r.mappings().all()
        except Exception as e:
            logger.warning("Experience vector recall failed: %s", e)
            rows = []
    else:
        rows = []

    results = []
    for row in rows:
        d = dict(row)
        d["similarity"] = float(d.get("similarity", 0))
        d["net_weight"] = (d.get("success_weight", 0) or 0) - (d.get("fail_count", 0) or 0) * EXPERIENCE_FAIL_PENALTY
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        if isinstance(d.get("updated_at"), datetime):
            d["updated_at"] = d["updated_at"].isoformat()
        results.append(d)
    return results


async def _experience_feedback(
    db: AsyncSession,
    experience_id: int,
    success: bool,
    note: str | None = None,
) -> dict:
    """Reinforcement: success +1 weight, fail +1 count + append note."""
    exp = await db.get(MemoryExperience, experience_id)
    if not exp:
        raise NotFound("经验不存在")
    if success:
        exp.success_weight = (exp.success_weight or 1) + 1
        exp.updated_at = datetime.now(timezone.utc)
    else:
        exp.fail_count = (exp.fail_count or 0) + 1
        existing = []
        if exp.fail_notes:
            try:
                existing = json.loads(exp.fail_notes) if isinstance(exp.fail_notes, str) else exp.fail_notes or []
            except (json.JSONDecodeError, TypeError):
                existing = []
        if note:
            existing.append({"note": note, "time": datetime.now(timezone.utc).isoformat()})
        exp.fail_notes = json.dumps(existing, ensure_ascii=False)
        exp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "id": experience_id,
        "success": success,
        "success_weight": exp.success_weight,
        "fail_count": exp.fail_count,
    }


async def _do_experience_dream(db: AsyncSession) -> dict:
    """Dream for experiences: merge near-duplicates, deactivate low-quality."""
    report = {"merged": 0, "deactivated": 0}

    # Merge near-duplicate active experiences
    try:
        merge_sql = text("""
            SELECT a.id AS keep_id, b.id AS drop_id,
                   (1 - (a.trigger_embedding <=> b.trigger_embedding)) AS similarity
            FROM memory_experiences a
            JOIN memory_experiences b ON a.id < b.id
            WHERE a.active = true AND b.active = true
              AND a.trigger_embedding IS NOT NULL
              AND b.trigger_embedding IS NOT NULL
              AND (1 - (a.trigger_embedding <=> b.trigger_embedding)) >= :threshold
            ORDER BY similarity DESC
        """)
        merge_candidates = await db.execute(merge_sql, {"threshold": EXPERIENCE_DEDUP_THRESHOLD})
        merge_rows = merge_candidates.mappings().all()
        dropped = set()
        for row in merge_rows:
            keep_id = row["keep_id"]
            drop_id = row["drop_id"]
            if keep_id in dropped or drop_id in dropped:
                continue
            keep = await db.get(MemoryExperience, keep_id)
            drop = await db.get(MemoryExperience, drop_id)
            if not keep or not drop:
                continue
            keep.success_weight = (keep.success_weight or 1) + (drop.success_weight or 1)
            keep.fail_count = (keep.fail_count or 0) + (drop.fail_count or 0)
            drop.active = False
            dropped.add(drop_id)
            report["merged"] += 1
    except Exception as e:
        logger.warning("Experience dream merge failed: %s", e)

    # Deactivate low-quality: net_weight <= 0 and fail_count >= 3
    try:
        deact_result = await db.execute(
            text("""
                UPDATE memory_experiences
                SET active = false
                WHERE active = true
                  AND (success_weight - fail_count * :penalty) <= 0
                  AND fail_count >= 3
            """),
            {"penalty": EXPERIENCE_FAIL_PENALTY},
        )
        report["deactivated"] = deact_result.rowcount
    except Exception as e:
        logger.warning("Experience dream deactivate failed: %s", e)

    await db.commit()
    return report


# ── SystemTaskQueue helper for post-save ─────────────────────────────

async def _enqueue_post_save(memory_id: int, content: str, source: str | None) -> None:
    """Enqueue post-save processing to SystemTaskQueue (non-blocking)."""
    try:
        from app.models.system import SystemTaskQueue
        import json
        async with AsyncSessionLocal() as eq_db:
            task = SystemTaskQueue(
                task_type="memory_post_save",
                parameters=json.dumps({
                    "memory_id": memory_id,
                    "content": content,
                    "source": source,
                }),
                status="pending",
                priority=0,
                module="memory",
            )
            eq_db.add(task)
            await eq_db.commit()
    except Exception as e:
        logger.warning("Post-save enqueue failed (non-fatal): %s", e)


# ── Cross-module Capabilities ───────────────────────────────────

async def _cap_save(params: dict, caller: str) -> dict:
    text = params.get("text", "")
    tags = params.get("tags")
    source = params.get("source", "auto-distill")
    conversation_id = params.get("conversation_id")
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    if not text.strip():
        raise ValidationError("内容不能为空")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory = MemoryRecord(
            owner_id=owner_id,
            text=text,
            tags=tags,
            source=source,
            conversation_id=conversation_id,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
    # Embedding synchronous, distillation async
    await _update_embedding(memory.id, text)
    await _enqueue_post_save(memory.id, text, source)
    return {"success": True, "data": {"id": memory.id}}


async def _cap_recall(params: dict, caller: str) -> dict:
    query = params.get("query", "")
    limit = params.get("limit", MEMORY_TOP_K_DEFAULT)
    expand_chain = params.get("expand_chain", False)
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        results = await _hybrid_recall(db, owner_id, query, limit, expand_chain)
    return {"success": True, "data": results}


async def _cap_fuse(params: dict, caller: str) -> dict:
    query = params.get("query", "")
    ids = params.get("ids", [])
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        result = await _do_fuse(db, owner_id, query, ids)
    return {"success": True, "data": result}


async def _cap_dream(params: dict, caller: str) -> dict:
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory_report = await _do_dream(db, owner_id)
        exp_report = await _do_experience_dream(db)
    return {"success": True, "data": {"memory": memory_report, "experience": exp_report}}


async def _cap_rethink(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    text = params.get("text", "")
    tags = params.get("tags")
    owner_id = _parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory = await db.get(MemoryRecord, mem_id)
        if not memory:
            raise NotFound("记忆不存在")
        if memory.owner_id != owner_id:
            raise PermissionDenied("只能编辑自己的记忆")
        memory.text = text
        if tags is not None:
            memory.tags = tags
        memory.source = "rethink"
        await db.commit()
    await _update_embedding(mem_id, text)
    await _enqueue_post_save(mem_id, text, "rethink")
    return {"success": True, "data": {"id": mem_id, "status": "rethought"}}


async def _cap_replace(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    old_text = params.get("old_text", "")
    new_text = params.get("new_text", "")
    owner_id = _parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory = await db.get(MemoryRecord, mem_id)
        if not memory:
            raise NotFound("记忆不存在")
        if memory.owner_id != owner_id:
            raise PermissionDenied("只能编辑自己的记忆")
        if old_text not in memory.text:
            raise ValidationError("未找到要替换的文本")
        memory.text = memory.text.replace(old_text, new_text, 1)
        memory.source = "edit"
        await db.commit()
    await _update_embedding(mem_id, memory.text)
    await _enqueue_post_save(mem_id, memory.text, "edit")
    return {"success": True, "data": {"id": mem_id, "status": "replaced"}}


async def _cap_insert(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    text = params.get("text", "")
    owner_id = _parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory = await db.get(MemoryRecord, mem_id)
        if not memory:
            raise NotFound("记忆不存在")
        if memory.owner_id != owner_id:
            raise PermissionDenied("只能编辑自己的记忆")
        memory.text += "\n" + text
        memory.source = "edit"
        await db.commit()
    await _update_embedding(mem_id, memory.text)
    await _enqueue_post_save(mem_id, memory.text, "edit")
    return {"success": True, "data": {"id": mem_id, "status": "inserted"}}


async def _cap_list(params: dict, caller: str) -> dict:
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        stmt = (
            select(MemoryRecord)
            .where(MemoryRecord.owner_id == owner_id)
            .order_by(MemoryRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        r = await db.execute(stmt)
        items = r.scalars().all()
    return {"success": True, "data": [_memory_to_dict(m) for m in items]}


async def _cap_delete(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    owner_id = _parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        memory = await db.get(MemoryRecord, mem_id)
        if not memory:
            raise NotFound("记忆不存在")
        if memory.owner_id != owner_id:
            raise PermissionDenied("只能删除自己的记忆")
        await db.execute(
            text("DELETE FROM memory_links WHERE from_id = :id OR to_id = :id"),
            {"id": mem_id},
        )
        await db.delete(memory)
        await db.commit()
    return {"success": True, "data": {"id": mem_id, "status": "deleted"}}


# ── Task Handler Registration ──────────────────────────────────


async def _handle_post_save(params: dict) -> dict:
    """Handle memory_post_save task from queue."""
    memory_id = params.get("memory_id")
    content = params.get("content", "")
    source = params.get("source")
    if not memory_id or not content:
        return {"error": "Missing required params"}
    await _post_save_process(memory_id, content, source)
    return {"status": "ok"}


register_task_handler("memory_post_save", _handle_post_save)


# ── Capability Registration ─────────────────────────────────────

register_capability(
    "memory", "save", _cap_save,
    description="保存一段记忆（事实/偏好/约定），自动提取摘要和向量用于语义检索",
    brief="记一条备忘",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "记忆内容"},
            "tags": {"type": "string", "description": "标签（可选，逗号分隔）"},
            "source": {"type": "string", "description": "来源（可选，如 auto-distill/user-save）"},
        },
        "required": ["text"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "recall", _cap_recall,
    description="语义检索自己的记忆（向量语义召回 + 重排 + 可选顺链扩展），不再仅靠关键词",
    brief="回忆我的备忘",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询（语义匹配）"},
            "limit": {"type": "integer", "description": "返回条数上限"},
            "expand_chain": {"type": "boolean", "description": "是否顺链扩展（沿语义关联带出相关记忆）"},
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "list", _cap_list,
    description="列出自己所有的记忆",
    brief="列出所有备忘",
    parameters={"type": "object", "properties": {
        "limit": {"type": "integer", "description": "返回条数上限"},
        "offset": {"type": "integer", "description": "偏移量"},
    }},
    min_role="viewer",
)

register_capability(
    "memory", "delete", _cap_delete,
    description="删除一条记忆",
    brief="删除一条备忘",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer", "description": "记忆 ID"}},
        "required": ["id"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "fuse", _cap_fuse,
    description="将多条记忆融合成贴合查询的一段简报（即时融合，on-demand）",
    brief="融合多条记忆",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "当前查询上下文"},
            "ids": {"type": "array", "items": {"type": "integer"}, "description": "要融合的记忆 ID 列表"},
        },
        "required": ["query", "ids"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "rethink", _cap_rethink,
    description="整条重写一条记忆（自编辑工具，如用户纠正错误时）",
    brief="重写一条记忆",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "记忆 ID"},
            "text": {"type": "string", "description": "新的完整内容"},
            "tags": {"type": "string", "description": "新标签（可选）"},
        },
        "required": ["id", "text"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "replace", _cap_replace,
    description="替换记忆中的某段文本（精确片段替换）",
    brief="替换记忆片段",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "记忆 ID"},
            "old_text": {"type": "string", "description": "要替换的旧文本"},
            "new_text": {"type": "string", "description": "新文本"},
        },
        "required": ["id", "old_text", "new_text"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "insert", _cap_insert,
    description="向已有记忆追加内容",
    brief="追加记忆",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "记忆 ID"},
            "text": {"type": "string", "description": "追加的内容"},
        },
        "required": ["id", "text"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "dream", _cap_dream,
    description="触发记忆自优化（去重合并 + 建链 + 衰减），后台运行不阻塞",
    brief="优化记忆库",
    parameters={"type": "object", "properties": {}},
    min_role="editor",
)


# ── Experience Capabilities ────────────────────────────────────────

async def _cap_save_experience(params: dict, caller: str) -> dict:
    """Save a success experience (distilled path)."""
    trigger_condition = params.get("trigger_condition", "")
    steps = params.get("steps", "")
    tools_used = params.get("tools_used")
    source_conversation_id = params.get("source_conversation_id")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        result = await _save_experience(db, trigger_condition, steps, tools_used, source_conversation_id)
    if result.get("error"):
        raise ValidationError(result["error"])
    return {"success": True, "data": result}


async def _cap_match_experience(params: dict, caller: str) -> dict:
    """Semantic match experiences for current user input."""
    query = params.get("query", "")
    limit = params.get("limit", 2)
    if not query.strip():
        return {"success": True, "data": []}
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        results = await _match_experience(db, query, limit)
    return {"success": True, "data": results}


async def _cap_experience_feedback(params: dict, caller: str) -> dict:
    """Reinforcement: mark experience as success or fail."""
    experience_id = params.get("experience_id")
    success = params.get("success", True)
    note = params.get("note")
    if not experience_id:
        raise ValidationError("experience_id required")
    await _ensure_init()
    async with AsyncSessionLocal() as db:
        result = await _experience_feedback(db, experience_id, success, note)
    if result.get("error"):
        raise ValidationError(result["error"])
    return {"success": True, "data": result}


register_capability(
    "memory", "save_experience", _cap_save_experience,
    description="保存一条成功经验（包含触发条件、有序步骤、工具列表），自动向量化并去重",
    brief="保存成功经验",
    parameters={
        "type": "object",
        "properties": {
            "trigger_condition": {"type": "string", "description": "触发条件（自然语言描述，如'用户想查看桌面目录'）"},
            "steps": {"type": "string", "description": "JSON 有序步骤：每步=意图+工具名+关键参数"},
            "tools_used": {"type": "string", "description": "JSON 列表：用到的能力列表"},
            "source_conversation_id": {"type": "integer", "description": "来源对话 id（可选）"},
        },
        "required": ["trigger_condition", "steps"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "match_experience", _cap_match_experience,
    description="语义匹配当前用户输入相关的成功经验（纯语义，零硬编码规则）",
    brief="匹配成功经验",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "当前用户输入（语义匹配）"},
            "limit": {"type": "integer", "description": "返回条数上限（默认 2）"},
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "experience_feedback", _cap_experience_feedback,
    description="反馈经验执行结果：成功则权重 +1，失败则失败次数 +1 并记录注释",
    brief="反馈经验结果",
    parameters={
        "type": "object",
        "properties": {
            "experience_id": {"type": "integer", "description": "经验 ID"},
            "success": {"type": "boolean", "description": "是否成功"},
            "note": {"type": "string", "description": "失败时的备注（可选）"},
        },
        "required": ["experience_id", "success"],
    },
    min_role="viewer",
)


# ── Admin overview stats capability ─────────────────────────────


async def _cap_overview_stats(params: dict, caller: str) -> dict:
    """Admin overview: aggregated memory & experience statistics.

    Returns counts, averages, and distribution data for system-wide monitoring.
    Requires admin role (enforced by register_capability min_role).
    """
    owner_id = _parse_user_id(caller)
    async with AsyncSessionLocal() as db:
        result = {}

        try:
            mem_count = await db.scalar(text("SELECT COUNT(*) FROM memory_records"))
            mem_with_embedding = await db.scalar(text("SELECT COUNT(*) FROM memory_records WHERE embedding IS NOT NULL"))
            mem_avg_confidence = await db.scalar(text("SELECT COALESCE(AVG(confidence), 0) FROM memory_records"))
            mem_avg_recency = await db.scalar(text("SELECT COALESCE(AVG(recency_score), 0) FROM memory_records"))
            mem_link_count = await db.scalar(text("SELECT COUNT(*) FROM memory_links"))
            mem_owner_count = await db.scalar(text("SELECT COUNT(DISTINCT owner_id) FROM memory_records"))
            result["memory"] = {
                "total_count": mem_count or 0,
                "with_embedding": mem_with_embedding or 0,
                "avg_confidence": round(float(mem_avg_confidence or 0), 3),
                "avg_recency_score": round(float(mem_avg_recency or 0), 3),
                "link_count": mem_link_count or 0,
                "owner_count": mem_owner_count or 0,
            }
        except Exception as e:
            logger.warning("Memory overview stats query failed: %s", e)
            result["memory"] = {"error": str(e)}

        try:
            exp_count = await db.scalar(text("SELECT COUNT(*) FROM memory_experiences"))
            exp_active = await db.scalar(text("SELECT COUNT(*) FROM memory_experiences WHERE active = true"))
            exp_inactive = await db.scalar(text("SELECT COUNT(*) FROM memory_experiences WHERE active = false"))
            exp_avg_weight = await db.scalar(text("SELECT COALESCE(AVG(success_weight), 0) FROM memory_experiences WHERE active = true"))
            exp_total_fails = await db.scalar(text("SELECT COALESCE(SUM(fail_count), 0) FROM memory_experiences"))
            result["experience"] = {
                "total_count": exp_count or 0,
                "active_count": exp_active or 0,
                "inactive_count": exp_inactive or 0,
                "avg_success_weight": round(float(exp_avg_weight or 0), 1),
                "total_fail_count": exp_total_fails or 0,
            }
        except Exception as e:
            logger.warning("Memory overview experience query failed: %s", e)
            result["experience"] = {"error": str(e)}

    return result


register_capability(
    "memory", "overview_stats", _cap_overview_stats,
    description="Admin overview: aggregated memory & experience statistics (total_count, with_embedding, avg_confidence, link_count, experience counts, etc.)",
    brief="记忆和经验的概览统计",
    parameters={},
    min_role="admin",
)
