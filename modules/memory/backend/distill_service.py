"""Memory distill service — cheap model summarization and keyword extraction.

Extracted from router.py to follow Router → Service → Model layering.
"""
import logging

logger = logging.getLogger("v2.memory").getChild("distill_service")

async def _call_cheap_model(messages: list[dict]) -> str:
    """调用便宜模型（models.json 配置），返回 content 文本。失败返回空字符串。"""
    try:
        from app.gateway.router import gateway_router
        result = await gateway_router.chat(messages=messages, profile_key=MEMORY_CHEAP_MODEL_KEY)
        return result.get("content", "") or ""
    except Exception as e:
        logger.warning("Cheap model call failed: %s", e)
        return ""


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

