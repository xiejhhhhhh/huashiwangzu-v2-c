import logging

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.task_worker import register_task_handler
from fastapi import APIRouter, Depends
from huashiwangzu_modules.memory.models import MemoryRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    DeleteMemoryRequest,
    FuseRequest,
    InsertRequest,
    RecallRequest,
    ReplaceRequest,
    RethinkRequest,
    SaveMemoryRequest,
)
from .services import capabilities as cap_mod
from .services import memory_service
from .services.distill_service import _hybrid_recall, _memory_to_dict

logger = logging.getLogger("v2.memory").getChild("router")

router = APIRouter(prefix="/api/memory", tags=["memory"])

MEMORY_CHEAP_MODEL_KEY = "deepseek-v4-flash"
MEMORY_TOP_K_DEFAULT = 5


# ── HTTP Endpoints ──────────────────────────────────────────────

@router.post("/save")
async def http_save(
    req: SaveMemoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    text = memory_service._require_non_empty_text(req.text, "text")
    memory = MemoryRecord(
        owner_id=current_user.id,
        text=text,
        tags=req.tags if req.tags else None,
        source=req.source or "user-save",
        conversation_id=req.conversation_id,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    embedding_updated = await memory_service._update_embedding(memory.id, text)
    post_save_enqueued = await memory_service._enqueue_post_save(memory.id, text, req.source)
    return ApiResponse(data={
        "id": memory.id,
        "status": "saved",
        "embedding_updated": embedding_updated,
        "post_save_enqueued": post_save_enqueued,
    })


@router.post("/recall")
async def http_recall(
    req: RecallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    query = memory_service._require_non_empty_text(req.query, "query")
    limit = memory_service._coerce_limit(req.limit, default=MEMORY_TOP_K_DEFAULT)
    results = await _hybrid_recall(db, current_user.id, query, limit, req.expand_chain)
    return ApiResponse(data=results)


@router.get("/list")
async def http_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
    limit: int = 50,
    offset: int = 0,
):
    await memory_service._ensure_init()
    safe_limit = memory_service._coerce_limit(limit, default=50, max_value=memory_service.MEMORY_LIST_LIMIT_MAX)
    safe_offset = memory_service._coerce_offset(offset, default=0)
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.owner_id == current_user.id)
        .order_by(MemoryRecord.created_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
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
    await memory_service._ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能删除自己的记忆")
    await memory_service._delete_memory_dependents(db, req.id)
    await db.delete(memory)
    await db.commit()
    return ApiResponse(data={"id": req.id, "status": "deleted"})


@router.post("/fuse")
async def http_fuse(
    req: FuseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    query = memory_service._require_non_empty_text(req.query, "query")
    ids = memory_service._coerce_id_list(req.ids, "ids")
    result = await memory_service._do_fuse(db, current_user.id, query, ids)
    return ApiResponse(data=result)


@router.post("/rethink")
async def http_rethink(
    req: RethinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    old_text = memory.text
    text = memory_service._require_non_empty_text(req.text, "text")
    memory.text = text
    if req.tags is not None:
        memory.tags = req.tags
    memory.source = "rethink"
    await db.commit()
    embedding_updated = await memory_service._update_embedding(memory.id, text)
    post_save_enqueued = await memory_service._enqueue_post_save(memory.id, text, "rethink")
    return ApiResponse(data={
        "id": memory.id,
        "status": "rethought",
        "old_text": old_text,
        "embedding_updated": embedding_updated,
        "post_save_enqueued": post_save_enqueued,
    })


@router.post("/replace")
async def http_replace(
    req: ReplaceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    old_text = memory_service._require_non_empty_text(req.old_text, "old_text")
    if not isinstance(req.new_text, str):
        raise ValidationError("new_text must be a string")
    if old_text not in memory.text:
        raise ValidationError("未找到要替换的文本")
    new_memory_text = memory.text.replace(old_text, req.new_text, 1)
    memory.text = new_memory_text
    memory.source = "edit"
    await db.commit()
    embedding_updated = await memory_service._update_embedding(memory.id, new_memory_text)
    post_save_enqueued = await memory_service._enqueue_post_save(memory.id, new_memory_text, "edit")
    return ApiResponse(data={
        "id": memory.id,
        "status": "replaced",
        "embedding_updated": embedding_updated,
        "post_save_enqueued": post_save_enqueued,
    })


@router.post("/insert")
async def http_insert(
    req: InsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    await memory_service._ensure_init()
    memory = await db.get(MemoryRecord, req.id)
    if not memory:
        raise NotFound("记忆不存在")
    if memory.owner_id != current_user.id:
        raise PermissionDenied("只能编辑自己的记忆")
    insert_text = memory_service._require_non_empty_text(req.text, "text")
    new_memory_text = memory.text + "\n" + insert_text
    memory.text = new_memory_text
    memory.source = "edit"
    await db.commit()
    embedding_updated = await memory_service._update_embedding(memory.id, new_memory_text)
    post_save_enqueued = await memory_service._enqueue_post_save(memory.id, new_memory_text, "edit")
    return ApiResponse(data={
        "id": memory.id,
        "status": "inserted",
        "embedding_updated": embedding_updated,
        "post_save_enqueued": post_save_enqueued,
    })


@router.post("/dream")
async def http_dream(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin")),
):
    await memory_service._ensure_init()
    result = await memory_service._do_dream(db, current_user.id)
    return ApiResponse(data=result)


# ── Task Handler Registration ──────────────────────────────────

async def _handle_post_save(params: dict) -> dict:
    memory_id = params.get("memory_id")
    content = params.get("content", "")
    source = params.get("source")
    if not memory_id or not content:
        return {"error": "Missing required params"}
    await memory_service._post_save_process(memory_id, content, source)
    return {"status": "ok"}

register_task_handler("memory_post_save", _handle_post_save)


# ── Capability Registration ─────────────────────────────────────

register_capability(
    "memory", "save", cap_mod._cap_save,
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
    "memory", "recall", cap_mod._cap_recall,
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
    "memory", "list", cap_mod._cap_list,
    description="列出自己所有的记忆",
    brief="列出所有备忘",
    parameters={"type": "object", "properties": {
        "limit": {"type": "integer", "description": "返回条数上限"},
        "offset": {"type": "integer", "description": "偏移量"},
    }},
    min_role="viewer",
)

register_capability(
    "memory", "delete", cap_mod._cap_delete,
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
    "memory", "fuse", cap_mod._cap_fuse,
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
    "memory", "rethink", cap_mod._cap_rethink,
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
    "memory", "replace", cap_mod._cap_replace,
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
    "memory", "insert", cap_mod._cap_insert,
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
    "memory", "dream", cap_mod._cap_dream,
    description="触发记忆自优化（去重合并 + 建链 + 衰减），后台运行不阻塞",
    brief="优化记忆库",
    parameters={"type": "object", "properties": {}},
    min_role="editor",
)

register_capability(
    "memory", "save_experience", cap_mod._cap_save_experience,
    description="保存一条成功经验（包含触发条件、有序步骤、工具列表），自动向量化并去重",
    brief="保存成功经验",
    parameters={
        "type": "object",
        "properties": {
            "trigger_condition": {"type": "string", "description": "触发条件（自然语言描述，如'用户想查看桌面目录'）"},
            "steps": {"type": "string", "description": "JSON 有序步骤：每步=意图+工具名+关键参数"},
            "tools_used": {"type": "string", "description": "JSON 列表：用到的能力列表"},
            "source_conversation_id": {"type": "integer", "description": "来源对话 id（可选）"},
            "scope": {"type": "string", "description": "经验范围：默认 user；global 仅系统 curated 通路可写"},
        },
        "required": ["trigger_condition", "steps"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "match_experience", cap_mod._cap_match_experience,
    description="语义匹配当前用户输入相关的成功经验（纯语义，零硬编码规则）",
    brief="匹配成功经验",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "当前用户输入（语义匹配）"},
            "limit": {"type": "integer", "description": "返回条数上限（默认 2）"},
            "team_owner_ids": {"type": "array", "items": {"type": "integer"}, "description": "系统通路可传的团队 owner id 列表"},
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "experience_feedback", cap_mod._cap_experience_feedback,
    description="反馈经验执行结果：成功则权重 +1，失败则失败次数 +1 并记录注释",
    brief="反馈经验结果",
    parameters={
        "type": "object",
        "properties": {
            "experience_id": {"type": "integer", "description": "经验 ID"},
            "success": {"type": "boolean", "description": "是否成功"},
            "note": {"type": "string", "description": "失败时的备注（可选）"},
            "team_owner_ids": {"type": "array", "items": {"type": "integer"}, "description": "系统通路可传的团队 owner id 列表"},
        },
        "required": ["experience_id", "success"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "overview_stats", cap_mod._cap_overview_stats,
    description="Admin overview: aggregated memory & experience statistics (total_count, with_embedding, avg_confidence, link_count, experience counts, etc.)",
    brief="记忆和经验的概览统计",
    parameters={},
    min_role="admin",
)

register_capability(
    "memory", "backfill_embeddings", cap_mod._cap_backfill_embeddings,
    description="Admin governance: safely backfill missing memory record embeddings with dry-run, owner, limit, and optional dream linking",
    brief="治理缺失记忆向量",
    parameters={
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "仅诊断不写入，默认 true"},
            "limit": {"type": "integer", "description": "本次最多处理条数，1-100，默认 20"},
            "owner_id": {"type": "integer", "description": "只治理指定 owner 的记忆，可选"},
            "owner": {"type": "integer", "description": "owner_id 的兼容别名，可选"},
            "run_dream": {"type": "boolean", "description": "成功回填后触发 dream 建链，可选"},
        },
    },
    min_role="admin",
)

register_capability(
    "memory", "recall_stable_rules", cap_mod._cap_recall_stable_rules,
    description="获取当前用户所有活跃的稳定规则记忆（项目边界、用户偏好、硬约束等），按优先级降序返回",
    brief="读取稳定规则",
    parameters={
        "type": "object",
        "properties": {
            "rule_types": {"type": "array", "items": {"type": "string"}, "description": "按类型过滤（可选），如 ['project_boundary', 'user_preference']"},
        },
    },
    min_role="viewer",
)

register_capability(
    "memory", "recall_chunk", cap_mod._cap_recall_chunk,
    description="语义检索 chunk 级记忆（带 provenance 溯源信息），返回最小粒度段落",
    brief="检索段落级记忆",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询（语义匹配）"},
            "limit": {"type": "integer", "description": "返回条数上限"},
        },
        "required": ["query"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "save_stable_rule", cap_mod._cap_save_stable_rule,
    description="保存一条稳定规则记忆（项目边界/用户偏好/硬约束/长期规则），不参与向量衰减",
    brief="保存稳定规则",
    parameters={
        "type": "object",
        "properties": {
            "rule_type": {"type": "string", "description": "规则类型：project_boundary / user_preference / hard_constraint / long_term_rule"},
            "content": {"type": "string", "description": "规则内容"},
            "priority": {"type": "integer", "description": "优先级（越高越重要）"},
            "source": {"type": "string", "description": "规则来源（可选）"},
        },
        "required": ["rule_type", "content"],
    },
    min_role="viewer",
)

register_capability(
    "memory", "backfill_links", cap_mod._cap_backfill_links,
    description="Admin governance: backfill missing memory_links between existing memory records using vector similarity. Dry-run safe.",
    brief="治理缺失记忆链接",
    parameters={
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "仅诊断不写入，默认 true"},
            "limit": {"type": "integer", "description": "最多处理条数，1-500，默认 50"},
            "owner_id": {"type": "integer", "description": "只治理指定 owner 的记忆，可选"},
        },
    },
    min_role="admin",
)

register_capability(
    "memory", "backfill_chunk_embeddings", cap_mod._cap_backfill_chunk_embeddings,
    description="Admin governance: safely backfill missing memory_chunk embeddings with dry-run support",
    brief="治理缺失 chunk 向量",
    parameters={
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "仅诊断不写入，默认 true"},
            "limit": {"type": "integer", "description": "本次最多处理条数，1-100，默认 20"},
            "owner_id": {"type": "integer", "description": "只治理指定 owner 的 chunk，可选"},
        },
    },
    min_role="admin",
)
