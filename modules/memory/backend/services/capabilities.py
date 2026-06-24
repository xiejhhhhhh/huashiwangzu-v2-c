import logging
from datetime import datetime

from sqlalchemy import select, text

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import AsyncSessionLocal

from huashiwangzu_modules.memory.models import MemoryRecord, MemoryLink, MemoryExperience, MemoryChunk, MemoryStableRule

from . import memory_service, experience_service, embedding_service
from .distill_service import _memory_to_dict

logger = logging.getLogger("v2.memory").getChild("capabilities")

MEMORY_TOP_K_DEFAULT = 5


async def _cap_save(params: dict, caller: str) -> dict:
    text = params.get("text", "")
    tags = params.get("tags")
    source = params.get("source", "auto-distill")
    conversation_id = params.get("conversation_id")
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    if not text.strip():
        raise ValidationError("内容不能为空")
    await memory_service._ensure_init()
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
    await memory_service._update_embedding(memory.id, text)
    await memory_service._enqueue_post_save(memory.id, text, source)
    return {"success": True, "data": {"id": memory.id}}


async def _cap_recall(params: dict, caller: str) -> dict:
    query = params.get("query", "")
    limit = params.get("limit", MEMORY_TOP_K_DEFAULT)
    expand_chain = params.get("expand_chain", False)
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await memory_service._ensure_init()
    from .distill_service import _hybrid_recall
    async with AsyncSessionLocal() as db:
        results = await _hybrid_recall(db, owner_id, query, limit, expand_chain)
    return {"success": True, "data": results}


async def _cap_fuse(params: dict, caller: str) -> dict:
    query = params.get("query", "")
    ids = params.get("ids", [])
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        result = await memory_service._do_fuse(db, owner_id, query, ids)
    return {"success": True, "data": result}


async def _cap_dream(params: dict, caller: str) -> dict:
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        memory_report = await memory_service._do_dream(db, owner_id)
        exp_report = await experience_service._do_experience_dream(db)
    return {"success": True, "data": {"memory": memory_report, "experience": exp_report}}


async def _cap_rethink(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    text = params.get("text", "")
    tags = params.get("tags")
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await memory_service._ensure_init()
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
    await memory_service._update_embedding(mem_id, text)
    await memory_service._enqueue_post_save(mem_id, text, "rethink")
    return {"success": True, "data": {"id": mem_id, "status": "rethought"}}


async def _cap_replace(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    old_text = params.get("old_text", "")
    new_text = params.get("new_text", "")
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await memory_service._ensure_init()
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
    await memory_service._update_embedding(mem_id, memory.text)
    await memory_service._enqueue_post_save(mem_id, memory.text, "edit")
    return {"success": True, "data": {"id": mem_id, "status": "replaced"}}


async def _cap_insert(params: dict, caller: str) -> dict:
    mem_id = params.get("id")
    text = params.get("text", "")
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id or not mem_id:
        raise ValidationError("参数不完整")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        memory = await db.get(MemoryRecord, mem_id)
        if not memory:
            raise NotFound("记忆不存在")
        if memory.owner_id != owner_id:
            raise PermissionDenied("只能编辑自己的记忆")
        memory.text += "\n" + text
        memory.source = "edit"
        await db.commit()
    await memory_service._update_embedding(mem_id, memory.text)
    await memory_service._enqueue_post_save(mem_id, memory.text, "edit")
    return {"success": True, "data": {"id": mem_id, "status": "inserted"}}


async def _cap_list(params: dict, caller: str) -> dict:
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    await memory_service._ensure_init()
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
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    await memory_service._ensure_init()
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


async def _cap_save_experience(params: dict, caller: str) -> dict:
    trigger_condition = params.get("trigger_condition", "")
    steps = params.get("steps", "")
    tools_used = params.get("tools_used")
    source_conversation_id = params.get("source_conversation_id")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        result = await experience_service._save_experience(db, trigger_condition, steps, tools_used, source_conversation_id)
    return {"success": True, "data": result}


async def _cap_match_experience(params: dict, caller: str) -> dict:
    query = params.get("query", "")
    limit = params.get("limit", 2)
    if not query.strip():
        return {"success": True, "data": []}
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        results = await experience_service._match_experience(db, query, limit)
    return {"success": True, "data": results}


async def _cap_experience_feedback(params: dict, caller: str) -> dict:
    experience_id = params.get("experience_id")
    success = params.get("success", True)
    note = params.get("note")
    if not experience_id:
        raise ValidationError("experience_id required")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        result = await experience_service._experience_feedback(db, experience_id, success, note)
    return {"success": True, "data": result}


async def _cap_overview_stats(params: dict, caller: str) -> dict:
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


# ── Three-layer memory capabilities ─────────────────────────────


async def _cap_recall_stable_rules(params: dict, caller: str) -> dict:
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    rule_types = params.get("rule_types", [])
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        from ..models import MemoryStableRule
        stmt = select(MemoryStableRule).where(
            MemoryStableRule.owner_id == owner_id,
            MemoryStableRule.active == True,
        )
        if rule_types:
            stmt = stmt.where(MemoryStableRule.rule_type.in_(rule_types))
        stmt = stmt.order_by(MemoryStableRule.priority.desc())
        r = await db.execute(stmt)
        items = r.scalars().all()
    return {"success": True, "data": [
        {
            "id": m.id,
            "rule_type": m.rule_type,
            "content": m.content,
            "priority": m.priority,
            "active": m.active,
            "source": m.source,
            "hit_count": m.hit_count,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in items
    ]}


async def _cap_recall_chunk(params: dict, caller: str) -> dict:
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    query = params.get("query", "")
    limit = params.get("limit", 5)
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        query_vec = await embedding_service._compute_embedding(query)
        if query_vec and len(query) > 3:
            vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
            sql = text(f"""
                SELECT id, memory_record_id, owner_id, text, summary, source, provenance,
                       conversation_id, chunk_index, confidence,
                       start_char, end_char, created_at,
                       (1 - (embedding <=> '{vec_literal}'::vector)) AS similarity
                FROM memory_chunks
                WHERE owner_id = :owner_id
                  AND embedding IS NOT NULL
                  AND (1 - (embedding <=> '{vec_literal}'::vector)) >= 0.3
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            r = await db.execute(sql, {"owner_id": owner_id, "limit": limit})
            rows = r.mappings().all()
            items = []
            for row in rows:
                d = dict(row)
                if isinstance(d.get("created_at"), datetime):
                    d["created_at"] = d["created_at"].isoformat()
                items.append(d)
        else:
            keyword = f"%{query}%"
            stmt = (
                select(MemoryChunk)
                .where(
                    MemoryChunk.owner_id == owner_id,
                    MemoryChunk.text.ilike(keyword),
                )
                .limit(limit)
            )
            r = await db.execute(stmt)
            items = [{
                "id": m.id,
                "memory_record_id": m.memory_record_id,
                "text": m.text,
                "summary": m.summary,
                "source": m.source,
                "provenance": m.provenance,
                "conversation_id": m.conversation_id,
                "chunk_index": m.chunk_index,
                "confidence": m.confidence,
                "start_char": m.start_char,
                "end_char": m.end_char,
                "similarity": 0.0,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            } for m in r.scalars().all()]
    return {"success": True, "data": items}


async def _cap_save_stable_rule(params: dict, caller: str) -> dict:
    owner_id = memory_service._parse_user_id(caller)
    if not owner_id:
        raise PermissionDenied("无法解析调用者身份")
    rule_type = params.get("rule_type", "general")
    content = params.get("content", "")
    priority = params.get("priority", 0)
    source = params.get("source")
    if not content.strip():
        raise ValidationError("规则内容不能为空")
    await memory_service._ensure_init()
    async with AsyncSessionLocal() as db:
        from ..models import MemoryStableRule
        rule = MemoryStableRule(
            owner_id=owner_id,
            rule_type=rule_type,
            content=content,
            priority=priority,
            source=source,
            active=True,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
    return {"success": True, "data": {"id": rule.id, "status": "created"}}
