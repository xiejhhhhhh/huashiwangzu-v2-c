import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationError

from huashiwangzu_modules.memory.models import MemoryExperience
from . import embedding_service

logger = logging.getLogger("v2.memory").getChild("experience_service")

EXPERIENCE_SIMILARITY_THRESHOLD = 0.3
EXPERIENCE_DEDUP_THRESHOLD = 0.85
EXPERIENCE_FAIL_PENALTY = 2


async def _experience_to_dict(exp) -> dict:
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
    if isinstance(steps, (list, dict)):
        steps = json.dumps(steps, ensure_ascii=False)
    if isinstance(tools_used, (list, dict)):
        tools_used = json.dumps(tools_used, ensure_ascii=False)
    if not (trigger_condition or "").strip() or not (steps or "").strip():
        raise ValidationError("trigger_condition and steps required")

    trigger_vec = await embedding_service._compute_embedding(trigger_condition)

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
                same_tools = False
                if isinstance(existing_steps, list) and isinstance(new_steps, list):
                    same_tools = len(existing_steps) == len(new_steps)
            except (json.JSONDecodeError, TypeError):
                same_tools = False
            if same_tools:
                await db.execute(
                    text("UPDATE memory_experiences SET success_weight = success_weight + 1, updated_at = NOW() WHERE id = :id"),
                    {"id": cand["id"]},
                )
                await db.commit()
                return {"id": cand["id"], "deduplicated": True, "success_weight": (cand["success_weight"] or 1) + 1}

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
    query_vec = await embedding_service._compute_embedding(query)
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
    report = {"merged": 0, "deactivated": 0}

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
