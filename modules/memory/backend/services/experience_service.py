import json
import logging
from datetime import datetime, timezone

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from huashiwangzu_modules.memory.models import MemoryExperience
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from . import embedding_service

logger = logging.getLogger("v2.memory").getChild("experience_service")

EXPERIENCE_SIMILARITY_THRESHOLD = 0.3
EXPERIENCE_DEDUP_THRESHOLD = 0.85
EXPERIENCE_FAIL_PENALTY = 2
EXPERIENCE_SCOPE_USER = "user"
EXPERIENCE_SCOPE_TEAM = "team"
EXPERIENCE_SCOPE_GLOBAL = "global"
EXPERIENCE_SCOPES = {EXPERIENCE_SCOPE_USER, EXPERIENCE_SCOPE_TEAM, EXPERIENCE_SCOPE_GLOBAL}
EXPERIENCE_MATCH_LIMIT_MAX = 20


def _is_system_caller(caller: str) -> bool:
    return bool(caller and caller.startswith("system:"))


def _parse_team_owner_ids(raw: object) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValidationError("team_owner_ids must be a list")
    result = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError) as exc:
            raise ValidationError("team_owner_ids must contain integers") from exc
        if value > 0:
            result.append(value)
    return result


def _coerce_match_limit(raw: object, default: int = 2) -> int:
    if raw in (None, ""):
        return default
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer") from exc
    if limit < 1 or limit > EXPERIENCE_MATCH_LIMIT_MAX:
        raise ValidationError(f"limit must be between 1 and {EXPERIENCE_MATCH_LIMIT_MAX}")
    return limit


def _coerce_bool(raw: object, name: str) -> bool:
    if not isinstance(raw, bool):
        raise ValidationError(f"{name} must be boolean")
    return raw


def _coerce_optional_positive_int(raw: object, name: str) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValidationError(f"{name} must be positive")
    return value


def _normalize_json_text(raw: object, name: str) -> str:
    if isinstance(raw, (list, dict)):
        return json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str):
        if not raw.strip():
            raise ValidationError(f"{name} cannot be empty")
        return raw
    raise ValidationError(f"{name} must be a string, list, or object")


def _normalize_optional_json_text(raw: object, name: str) -> str | None:
    if raw in (None, ""):
        return None
    return _normalize_json_text(raw, name)


def _resolve_experience_write_scope(
    caller: str,
    caller_owner_id: int | None,
    requested_scope: str | None = None,
    requested_owner_id: int | None = None,
) -> tuple[int | None, str]:
    scope = (requested_scope or "").strip().lower()
    if not scope:
        scope = EXPERIENCE_SCOPE_GLOBAL if _is_system_caller(caller) and not caller_owner_id else EXPERIENCE_SCOPE_USER
    if scope not in EXPERIENCE_SCOPES:
        raise ValidationError("scope must be user/team/global")
    target_owner_id = _coerce_optional_positive_int(requested_owner_id, "owner_id")

    if scope == EXPERIENCE_SCOPE_GLOBAL:
        if not _is_system_caller(caller):
            raise PermissionDenied("全局经验只能由系统 curated 通路写入")
        return None, EXPERIENCE_SCOPE_GLOBAL

    if scope == EXPERIENCE_SCOPE_TEAM:
        if not _is_system_caller(caller):
            raise PermissionDenied("团队经验必须由系统通路写入")
        if not target_owner_id:
            raise ValidationError("team scope requires owner_id")
        return target_owner_id, EXPERIENCE_SCOPE_TEAM

    if caller_owner_id:
        return caller_owner_id, EXPERIENCE_SCOPE_USER
    if _is_system_caller(caller) and target_owner_id:
        return target_owner_id, EXPERIENCE_SCOPE_USER
    raise PermissionDenied("无法解析调用者身份")


def _access_condition(owner_id: int | None, team_owner_ids: list[int]) -> tuple[str, dict]:
    clauses = ["COALESCE(scope, 'global') = 'global'"]
    params: dict = {}
    if owner_id:
        clauses.append("(scope = 'user' AND owner_id = :owner_id)")
        params["owner_id"] = owner_id
    if team_owner_ids:
        clauses.append("(scope = 'team' AND owner_id = ANY(CAST(:team_owner_ids AS INTEGER[])))")
        params["team_owner_ids"] = team_owner_ids
    return "(" + " OR ".join(clauses) + ")", params


def _scope_owner_condition(scope: str, owner_id: int | None) -> tuple[str, dict]:
    if owner_id is None:
        return "scope = :scope AND owner_id IS NULL", {"scope": scope}
    return "scope = :scope AND owner_id = :scope_owner_id", {"scope": scope, "scope_owner_id": owner_id}


def _aliased_scope_owner_condition(alias: str, scope: str, owner_id: int | None) -> str:
    if owner_id is None:
        return f"COALESCE({alias}.scope, 'global') = :scope AND {alias}.owner_id IS NULL"
    return f"{alias}.scope = :scope AND {alias}.owner_id = :scope_owner_id"


async def _experience_to_dict(exp) -> dict:
    return {
        "id": exp.id,
        "owner_id": exp.owner_id,
        "scope": exp.scope,
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
    *,
    owner_id: int | None = None,
    scope: str = EXPERIENCE_SCOPE_USER,
) -> dict:
    steps = _normalize_json_text(steps, "steps")
    tools_used = _normalize_optional_json_text(tools_used, "tools_used")
    source_conversation_id = _coerce_optional_positive_int(source_conversation_id, "source_conversation_id")
    if not (trigger_condition or "").strip():
        raise ValidationError("trigger_condition and steps required")

    scope_owner_sql, scope_owner_params = _scope_owner_condition(scope, owner_id)
    exact_result = await db.execute(
        text(f"""
            UPDATE memory_experiences
            SET success_weight = COALESCE(success_weight, 1) + 1,
                updated_at = NOW()
            WHERE active = true
              AND {scope_owner_sql}
              AND trigger_condition = :trigger_condition
              AND steps = :steps
            RETURNING id, success_weight
        """),
        {
            **scope_owner_params,
            "trigger_condition": trigger_condition,
            "steps": steps,
        },
    )
    exact_row = exact_result.mappings().first()
    if exact_row:
        await db.commit()
        return {"id": exact_row["id"], "deduplicated": True, "success_weight": exact_row["success_weight"]}

    trigger_vec = await embedding_service._compute_embedding(trigger_condition)
    if trigger_vec:
        try:
            vec_literal = embedding_service._vector_literal(trigger_vec)
            if not vec_literal:
                raise ValueError("invalid embedding vector")
            sql = text(f"""
                SELECT id, trigger_condition, steps, success_weight
                FROM memory_experiences
                WHERE active = true
                  AND {scope_owner_sql}
                  AND trigger_embedding IS NOT NULL
                  AND (1 - (trigger_embedding <=> CAST(:query_vec AS vector(1024)))) >= :threshold
                ORDER BY (1 - (trigger_embedding <=> CAST(:query_vec AS vector(1024)))) DESC
                LIMIT 3
            """)
            r = await db.execute(sql, {**scope_owner_params, "threshold": EXPERIENCE_DEDUP_THRESHOLD, "query_vec": vec_literal})
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
                update_result = await db.execute(
                    text(f"""
                        UPDATE memory_experiences
                        SET success_weight = COALESCE(success_weight, 1) + 1,
                            updated_at = NOW()
                        WHERE id = :id
                          AND {scope_owner_sql}
                        RETURNING success_weight
                    """),
                    {**scope_owner_params, "id": cand["id"]},
                )
                updated = update_result.mappings().first()
                await db.commit()
                return {
                    "id": cand["id"],
                    "deduplicated": True,
                    "success_weight": updated["success_weight"] if updated else (cand["success_weight"] or 1) + 1,
                }

    trigger_vec_literal = embedding_service._vector_literal(trigger_vec) if trigger_vec else None
    inserted = await db.execute(
        text("""
            INSERT INTO memory_experiences (
                owner_id, scope, trigger_condition, trigger_embedding, steps,
                tools_used, source_conversation_id, active, created_at, updated_at
            )
            VALUES (
                :owner_id, :scope, :trigger_condition, CAST(:trigger_vec AS vector(1024)), :steps,
                :tools_used, :source_conversation_id, true, NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
            RETURNING id, success_weight
        """),
        {
            "owner_id": owner_id,
            "scope": scope,
            "trigger_condition": trigger_condition,
            "trigger_vec": trigger_vec_literal,
            "steps": steps,
            "tools_used": tools_used,
            "source_conversation_id": source_conversation_id,
        },
    )
    insert_row = inserted.mappings().first()
    await db.commit()
    if insert_row:
        return {"id": insert_row["id"], "deduplicated": False, "success_weight": insert_row["success_weight"]}

    duplicate_result = await db.execute(
        text(f"""
            UPDATE memory_experiences
            SET success_weight = COALESCE(success_weight, 1) + 1,
                updated_at = NOW()
            WHERE active = true
              AND {scope_owner_sql}
              AND trigger_condition = :trigger_condition
              AND steps = :steps
            RETURNING id, success_weight
        """),
        {
            **scope_owner_params,
            "trigger_condition": trigger_condition,
            "steps": steps,
        },
    )
    duplicate_row = duplicate_result.mappings().first()
    await db.commit()
    if duplicate_row:
        return {"id": duplicate_row["id"], "deduplicated": True, "success_weight": duplicate_row["success_weight"]}
    raise ValidationError("经验保存失败")


async def _match_experience(
    db: AsyncSession,
    query: str,
    limit: int = 2,
    *,
    owner_id: int | None = None,
    team_owner_ids: list[int] | None = None,
) -> list[dict]:
    limit = _coerce_match_limit(limit)
    query_vec = await embedding_service._compute_embedding(query)
    access_sql, access_params = _access_condition(owner_id, team_owner_ids or [])
    if query_vec:
        try:
            vec_literal = embedding_service._vector_literal(query_vec)
            if not vec_literal:
                raise ValueError("invalid embedding vector")
            sql = text(f"""
                SELECT id, owner_id, COALESCE(scope, 'global') AS scope,
                       trigger_condition, steps, tools_used,
                       success_weight, fail_count, fail_notes,
                       source_conversation_id, created_at, updated_at,
                       (1 - (trigger_embedding <=> CAST(:query_vec AS vector(1024)))) AS similarity,
                       CASE COALESCE(scope, 'global')
                           WHEN 'user' THEN 0
                           WHEN 'team' THEN 1
                           ELSE 2
                       END AS scope_rank
                FROM memory_experiences
                WHERE active = true
                  AND {access_sql}
                  AND trigger_embedding IS NOT NULL
                  AND (1 - (trigger_embedding <=> CAST(:query_vec AS vector(1024)))) >= :threshold
                ORDER BY scope_rank ASC,
                         (success_weight - fail_count * :penalty) DESC,
                         similarity DESC
                LIMIT :limit
            """)
            r = await db.execute(sql, {
                **access_params,
                "query_vec": vec_literal,
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

    if not rows:
        keyword = f"%{query}%"
        fallback_sql = text(f"""
            SELECT id, owner_id, COALESCE(scope, 'global') AS scope,
                   trigger_condition, steps, tools_used,
                   success_weight, fail_count, fail_notes,
                   source_conversation_id, created_at, updated_at,
                   0.0 AS similarity,
                   CASE COALESCE(scope, 'global')
                       WHEN 'user' THEN 0
                       WHEN 'team' THEN 1
                       ELSE 2
                   END AS scope_rank
            FROM memory_experiences
            WHERE active = true
              AND {access_sql}
              AND (
                  trigger_condition ILIKE :keyword
                  OR steps ILIKE :keyword
                  OR tools_used ILIKE :keyword
              )
            ORDER BY scope_rank ASC,
                     (success_weight - fail_count * :penalty) DESC,
                     updated_at DESC
            LIMIT :limit
        """)
        r = await db.execute(fallback_sql, {
            **access_params,
            "keyword": keyword,
            "penalty": EXPERIENCE_FAIL_PENALTY,
            "limit": limit,
        })
        rows = r.mappings().all()

    results = []
    for row in rows:
        d = dict(row)
        d["similarity"] = float(d.get("similarity", 0))
        d["net_weight"] = (d.get("success_weight", 0) or 0) - (d.get("fail_count", 0) or 0) * EXPERIENCE_FAIL_PENALTY
        d.pop("scope_rank", None)
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
    *,
    owner_id: int | None = None,
    team_owner_ids: list[int] | None = None,
) -> dict:
    experience_id = _coerce_optional_positive_int(experience_id, "experience_id")
    if experience_id is None:
        raise ValidationError("experience_id required")
    success = _coerce_bool(success, "success")
    if note is not None and not isinstance(note, str):
        raise ValidationError("note must be a string")
    access_sql, access_params = _access_condition(owner_id, team_owner_ids or [])
    if success:
        result = await db.execute(
            text(f"""
                UPDATE memory_experiences
                SET success_weight = COALESCE(success_weight, 1) + 1,
                    updated_at = NOW()
                WHERE id = :id
                  AND {access_sql}
                RETURNING id, success_weight, fail_count
            """),
            {**access_params, "id": experience_id},
        )
    else:
        note_payload = None
        if note:
            note_payload = json.dumps([{"note": note, "time": datetime.now(timezone.utc).isoformat()}], ensure_ascii=False)
        result = await db.execute(
            text(f"""
                UPDATE memory_experiences
                SET fail_count = COALESCE(fail_count, 0) + 1,
                    fail_notes = CASE
                        WHEN :has_note = false THEN fail_notes
                        ELSE (COALESCE(NULLIF(fail_notes, ''), '[]')::jsonb || CAST(:note_payload AS jsonb))::text
                    END,
                    updated_at = NOW()
                WHERE id = :id
                  AND {access_sql}
                RETURNING id, success_weight, fail_count
            """),
            {
                **access_params,
                "id": experience_id,
                "has_note": note_payload is not None,
                "note_payload": note_payload or "[]",
            },
        )
    row = result.mappings().first()
    if not row:
        exists = await db.scalar(text("SELECT 1 FROM memory_experiences WHERE id = :id"), {"id": experience_id})
        if exists:
            raise PermissionDenied("只能反馈自己或可见范围内的经验")
        raise NotFound("经验不存在")
    await db.commit()
    return {
        "id": experience_id,
        "success": success,
        "success_weight": row["success_weight"],
        "fail_count": row["fail_count"],
    }


async def _do_experience_dream(
    db: AsyncSession,
    owner_id: int | None = None,
    scope: str = EXPERIENCE_SCOPE_USER,
) -> dict:
    report = {"merged": 0, "deactivated": 0}
    scope_owner_sql, scope_owner_params = _scope_owner_condition(scope, owner_id)
    scope_owner_sql_a = _aliased_scope_owner_condition("a", scope, owner_id)
    scope_owner_sql_b = _aliased_scope_owner_condition("b", scope, owner_id)

    try:
        merge_sql = text(f"""
            SELECT a.id AS keep_id, b.id AS drop_id,
                   (1 - (a.trigger_embedding <=> b.trigger_embedding)) AS similarity
            FROM memory_experiences a
            JOIN memory_experiences b ON a.id < b.id
            WHERE a.active = true AND b.active = true
              AND {scope_owner_sql_a}
              AND {scope_owner_sql_b}
              AND a.trigger_embedding IS NOT NULL
              AND b.trigger_embedding IS NOT NULL
              AND (1 - (a.trigger_embedding <=> b.trigger_embedding)) >= :threshold
            ORDER BY similarity DESC
        """)
        merge_params = {**scope_owner_params, "threshold": EXPERIENCE_DEDUP_THRESHOLD}
        merge_candidates = await db.execute(merge_sql, merge_params)
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
            text(f"""
                UPDATE memory_experiences
                SET active = false
                WHERE active = true
                  AND {scope_owner_sql}
                  AND (success_weight - fail_count * :penalty) <= 0
                  AND fail_count >= 3
            """),
            {**scope_owner_params, "penalty": EXPERIENCE_FAIL_PENALTY},
        )
        report["deactivated"] = deact_result.rowcount
    except Exception as e:
        logger.warning("Experience dream deactivate failed: %s", e)

    await db.commit()
    return report
