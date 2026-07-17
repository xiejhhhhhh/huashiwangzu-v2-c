"""内容摄取阶段 DAG（方案07 §17-§20，WP2）。

单一 task_type `content_ingest_stage`：一个任务跑一个阶段，settlement 在
Dispatcher 的 fenced 事务里发后继阶段。链路：

    package_ensure → canonical_parse → resource_extract → derivative_build → knowledge_register

本轮（§24）越过模型密集节点：
- canonical_parse 对需 VLM 的格式（纯图/image-vision）降级 metadata_only，标
  skipped(model_budget_deferred)，不假绿。
- knowledge_register 恒 skipped(model_budget_deferred)（embedding 越过）。

1:1 参照 modules/knowledge/backend/services/pipeline_service.py 的 handler+settlement 骨架，
不重造 Dispatcher 调度底座。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.ingestion_status import (
    MODEL_BUDGET_DEFERRED_REASON,
    STAGE_DAG,
)
from app.database import AsyncSessionLocal
from app.models.content import ContentPackageVersion, ResourceRef
from app.models.file import File, FileDerivative
from app.services.content import ingestion_run_store as run_store
from app.services.content.package_service import (
    ContentPackageService,
    _get_parser_for_format,
)
from app.services.task_dispatcher import (
    TaskDefinition,
    publish_task,
    register_dispatcher_reconciler,
    register_task_definition,
    register_task_settlement_handler,
    unpack_task_parameters,
)
from app.services.task_worker import register_task_handler

logger = logging.getLogger("v2.content").getChild("ingest")

INGEST_TASK_TYPE = "content_ingest_stage"

# 需模型的解析器（本轮越过）——只有图片走 VLM(image-vision:describe)。
MODEL_NEEDING_PARSER_MODULES = {"image-vision"}

# 每阶段的 lane 分配（本轮 knowledge_register 直接 skipped，不真占 lane）。
STAGE_LANE = {
    "package_ensure": "local_preprocess",
    "canonical_parse": "local_preprocess",
    "resource_extract": "local_preprocess",
    "derivative_build": "local_preprocess",
    "knowledge_register": "derived_index",
}


def _caller_of(owner_id: int) -> str:
    return f"user:{int(owner_id)}"


def _next_stage(stage: str) -> str | None:
    try:
        idx = STAGE_DAG.index(stage)
    except ValueError:
        return None
    return STAGE_DAG[idx + 1] if idx + 1 < len(STAGE_DAG) else None


# ── 单阶段执行 ─────────────────────────────────────────────────────────────
# 每个 stage fn 返回 dict：{status: done|degraded|skipped|failed, reason, ...}
# handler 在自己的事务里 commit，settlement 只发后继。

async def _stage_package_ensure(db: AsyncSession, body: dict, file: File) -> dict[str, Any]:
    """确保 ContentPackage 存在并绑定 source_file。幂等：get_or_create 天然幂等。"""
    svc = ContentPackageService()
    pkg = await svc.get_or_create(db, file.id, file.owner_id, _caller_of(file.owner_id))
    return {"status": "done", "package_id": pkg["id"]}


async def _stage_canonical_parse(db: AsyncSession, body: dict, file: File) -> dict[str, Any]:
    """解析出 CanonicalIR，写 ContentPackageVersion。

    §24：需 VLM 的格式（image-vision）降级 metadata_only，标 skipped(model_budget_deferred)。
    幂等：run 已有 package_version_id 且 source_sha256 未变 → 返回既有 version。
    """
    run_id = body["run_id"]
    package_id = int(body["package_id"])
    ext = (file.extension or "").lower()

    run = await run_store.get_run(db, run_id)
    if run is not None and run.package_version_id and run.source_sha256 == body.get("source_sha256"):
        return {"status": "done", "package_version_id": run.package_version_id, "idempotent": True}

    parser = _get_parser_for_format(ext)
    # 越过模型：图片(VLM)本轮不跑，落 metadata_only 版本，标 deferred。
    if parser and parser[0] in MODEL_NEEDING_PARSER_MODULES:
        version_id = await _write_metadata_only_version(db, package_id, file, reason=MODEL_BUDGET_DEFERRED_REASON)
        return {
            "status": "skipped",
            "reason": MODEL_BUDGET_DEFERRED_REASON,
            "package_version_id": version_id,
            "metadata_only": True,
        }

    svc = ContentPackageService()
    try:
        result = await svc.run_pipeline(db, package_id, _caller_of(file.owner_id))
    except Exception as exc:  # 解析器不可用/格式不支持等
        logger.warning("canonical_parse failed file_id=%s: %s", file.id, exc)
        return {"status": "failed", "reason": str(exc)[:300]}

    status = str(result.get("status") or "parsed")
    ver = await svc._get_current_version(db, package_id)
    version_id = ver.id if ver else None
    # parsed→done, degraded→degraded（部分资源降级仍可用）
    return {
        "status": "degraded" if status == "degraded" else "done",
        "package_version_id": version_id,
        "package_status": status,
    }


async def _stage_resource_extract(db: AsyncSession, body: dict, file: File) -> dict[str, Any]:
    """把 IR 里引用的资源登记为 ResourceRef。

    §24：结构抽取（图片字节存 Resource、建 Ref）正常跑；OCR/VLM 文字描述本轮不做。
    幂等：该 version 已有 ResourceRef → 跳过重抽。
    """
    package_id = int(body["package_id"])
    svc = ContentPackageService()
    version = await svc._get_current_version(db, package_id)
    if not version or not version.content_json:
        return {"status": "done", "reason": "no_version_or_empty", "resource_count": 0}

    existing = await db.scalar(
        select(func.count(ResourceRef.id)).where(ResourceRef.version_id == version.id)
    )
    if int(existing or 0) > 0:
        return {"status": "done", "idempotent": True, "resource_count": int(existing)}

    # 复用同步管线的资源抽取（结构性：把 block.resource_ref 建成 ResourceRef）。
    from app.services.content.pipeline_service import ContentPipelineService

    pipeline = ContentPipelineService()
    await pipeline._extract_resources(db, package_id, _caller_of(file.owner_id))
    count = await db.scalar(
        select(func.count(ResourceRef.id)).where(ResourceRef.version_id == version.id)
    )
    return {"status": "done", "resource_count": int(count or 0)}


async def _stage_derivative_build(db: AsyncSession, body: dict, file: File) -> dict[str, Any]:
    """生成派生物（预览图/标准图）。纯结构，不需模型。

    幂等：FileDerivative 唯一键 (file_id, kind) 已存在 → 跳过。
    """
    existing = await db.scalar(
        select(func.count(FileDerivative.id)).where(FileDerivative.file_id == file.id)
    )
    if int(existing or 0) > 0:
        return {"status": "done", "idempotent": True, "derivative_count": int(existing)}

    try:
        from app.services.image_derivative_service import ensure_standard_image_derivative

        await ensure_standard_image_derivative(db, file.id)
    except Exception as exc:
        # 派生物是尽力而为，失败降级不阻塞（原上传路径也是吞掉异常的）。
        logger.info("derivative_build best-effort skip file_id=%s: %s", file.id, exc)
        return {"status": "degraded", "reason": f"derivative_skip:{str(exc)[:120]}"}
    count = await db.scalar(
        select(func.count(FileDerivative.id)).where(FileDerivative.file_id == file.id)
    )
    return {"status": "done", "derivative_count": int(count or 0)}


async def _stage_knowledge_register(db: AsyncSession, body: dict, file: File) -> dict[str, Any]:
    """注册进知识库（分块+embedding）。§24：本轮整阶段越过（embedding 烧额度）。

    恒 skipped(model_budget_deferred)，天然幂等，额度恢复后 replay 重入。
    """
    return {"status": "skipped", "reason": MODEL_BUDGET_DEFERRED_REASON}


_STAGE_FUNCS = {
    "package_ensure": _stage_package_ensure,
    "canonical_parse": _stage_canonical_parse,
    "resource_extract": _stage_resource_extract,
    "derivative_build": _stage_derivative_build,
    "knowledge_register": _stage_knowledge_register,
}


async def _write_metadata_only_version(
    db: AsyncSession, package_id: int, file: File, *, reason: str,
) -> int | None:
    """需模型格式的降级落盘：写一个只有元信息、无语义正文的 version，标记 deferred。

    让 Viewer/下游能拿到"文件存在但语义待模型"的明确状态，而不是空白或假绿。
    """
    from app.contracts.content_hash import content_sha256
    from app.models.content import ContentPackage

    pkg = await db.get(ContentPackage, package_id)
    if pkg is None:
        return None
    ext = (file.extension or "").lower()
    manifest = {
        "title": file.name or "",
        "source_file_id": file.id,
        "extension": ext,
        "package_type": pkg.package_type,
        "created_by_parser": "ingest:metadata_only",
        "parser_version": "1.0",
        "source_hash": pkg.source_hash or "",
        "deferred": {"stage": "canonical_parse", "reason": reason},
    }
    content_ir = {
        "manifest": manifest,
        "blocks": [],
        "parse_status": "skipped",
        "deferred_reason": reason,
    }
    content_json = json.dumps(content_ir, ensure_ascii=False)

    # metadata_only 同时写 content_json + canonical 骨架，诚实反映 deferred，不假绿。
    canonical_json = None
    canonical_profile = None
    canonical_content_sha = None
    canonical_fidelity = None
    try:
        from app.services.content.canonical_normalizer import normalize_parser_output

        canonical_ir = normalize_parser_output(
            content_ir, file_id=file.id, extension=ext,
            source_sha256=pkg.source_hash or None,
            original_name=file.name or "", size=file.size or 0,
        )
        canonical_json = canonical_ir.model_dump_json()
        canonical_profile = canonical_ir.profile
        canonical_content_sha = content_sha256(canonical_ir)
        canonical_fidelity = canonical_ir.fidelity.level
    except Exception as exc:  # 骨架归一失败不阻塞降级落盘
        logger.warning("metadata_only canonical skip file_id=%s: %s", file.id, exc)

    version_no = 1
    last = await db.scalar(
        select(ContentPackageVersion.version_no)
        .where(ContentPackageVersion.package_id == package_id)
        .order_by(ContentPackageVersion.version_no.desc())
        .limit(1)
    )
    if last:
        version_no = int(last) + 1
    version = ContentPackageVersion(
        package_id=package_id,
        version_no=version_no,
        content_json=content_json,
        canonical_json=canonical_json,
        schema_version="canonical-content-ir/v1" if canonical_json else None,
        profile=canonical_profile,
        content_sha256=canonical_content_sha,
        source_sha256=pkg.source_hash or None,
        fidelity_level=canonical_fidelity,
        summary=f"metadata_only (deferred: {reason})",
        operation_type="parse",
        created_by=file.owner_id,
    )
    db.add(version)
    await db.flush()
    pkg.current_version_id = version.id
    pkg.manifest_json = json.dumps(manifest, ensure_ascii=False)
    if canonical_profile:
        pkg.profile = canonical_profile
        pkg.schema_version = "canonical-content-ir/v1"
    # 降级但可用：状态给 degraded，明确"部分特性未支持"，而非 ready 假绿。
    pkg.status = "degraded"
    pkg.parse_error = None
    return version.id


def _budget_skip(reason: str | None) -> bool:
    return str(reason or "") == MODEL_BUDGET_DEFERRED_REASON


async def _publish_stage(
    db: AsyncSession, *, run_id: str, file_id: int, package_id: int | None,
    source_revision_id: int | None, source_sha256: str | None,
    pipeline_version: str, generation: int, stage: str, owner_id: int,
) -> None:
    """在调用方事务里发一个阶段任务（flush-only，不 commit）。"""
    await publish_task(
        db,
        task_type=INGEST_TASK_TYPE,
        module="content",
        owner_id=owner_id,
        body={
            "run_id": run_id,
            "file_id": file_id,
            "package_id": package_id,
            "source_revision_id": source_revision_id,
            "source_sha256": source_sha256,
            "pipeline_version": pipeline_version,
            "generation": generation,
            "stage": stage,
        },
        requested_by=f"user:{owner_id}",
        trigger="ingest",
        document_id=file_id,
        stage_key=stage,
        lane_key=STAGE_LANE.get(stage, "local_preprocess"),
        ready_status="ready",
    )


async def _ingest_stage_handler(params: dict) -> dict[str, Any]:
    """跑一个摄取阶段。handler 只负责本阶段 + commit；后继阶段由 settlement 发。

    task_worker 已把 envelope.body 展平进 params，故这里 params 即 body。
    """
    stage = str(params.get("stage") or "")
    run_id = str(params.get("run_id") or "")
    file_id = int(params.get("file_id") or 0)
    if stage not in _STAGE_FUNCS or not run_id or not file_id:
        return {"status": "failed", "reason": f"bad_params stage={stage} run={run_id} file={file_id}"}

    async with AsyncSessionLocal() as db:
        run = await run_store.get_run(db, run_id)
        if run is None:
            return {"status": "failed", "reason": f"run {run_id} not found"}

        # 取消检查：打了取消标记 → 主动落 cancelled，不再干活。
        if run.cancel_requested:
            await run_store.transition(
                db, run_id, expected_lock_version=run.lock_version,
                to_status="cancelled", error_message="cancelled_by_request",
            )
            await db.commit()
            return {"status": "skipped", "reason": "cancelled", "stage": stage, "run_id": run_id, "terminal_run": True}

        file = await db.get(File, file_id)
        if file is None or file.deleted:
            await run_store.mark_failed(db, run, error_code="file_missing", error_message=f"file {file_id} missing")
            await db.commit()
            return {"status": "failed", "reason": "file_missing", "stage": stage, "run_id": run_id}

        # 首阶段把 run 从 queued 推到 running（幂等：非 queued 就不动）。
        if run.status == "queued":
            await run_store.mark_running(db, run)

        stage_fn = _STAGE_FUNCS[stage]
        try:
            result = await stage_fn(db, params, file)
        except Exception as exc:
            logger.exception("ingest stage %s failed file_id=%s", stage, file_id)
            await db.rollback()
            return {"status": "failed", "reason": str(exc)[:300], "stage": stage, "run_id": run_id}

        await db.commit()

        result.update({"stage": stage, "run_id": run_id, "file_id": file_id})
        # 失败让 dispatcher 走重试；这里不发后继。settlement 只在成功后被调。
        return result


async def _settle_ingest_task(db: AsyncSession, task, result: dict[str, Any]) -> None:
    """在 Dispatcher 的 fenced 事务里推进 DAG：成功阶段 → 发后继；末阶段 → 收口 run。"""
    status = str(result.get("status") or "")
    reason = result.get("reason")
    if status == "failed":
        return  # 失败由 dispatcher 重试；终态失败由 reconciler 收口 run。
    if result.get("terminal_run"):
        return  # 已在 handler 里落终态（如 cancelled）。

    params = unpack_task_parameters(task.parameters)
    run_id = str(params.get("run_id") or "")
    stage = str(task.stage_key or params.get("stage") or "")
    file_id = int(task.document_id or params.get("file_id") or 0)
    if not run_id or not stage:
        return
    run = await run_store.get_run(db, run_id)
    if run is None or run.status in run_store.TERMINAL_STATUSES:
        return

    # package_ensure 刚建/取了 package → 其 id 只在 result 里，params/run 可能还是 None。
    # 优先级：result > run.package_id > params，解析后回填到 run，供后继阶段与重放使用。
    pkg_version_id = result.get("package_version_id")
    package_id = result.get("package_id") or run.package_id or params.get("package_id")
    package_id = int(package_id) if package_id else None

    # 把新知道的 package_id / version_id 回填到 run（乐观锁；一次跃迁同时写两者）。
    run_patch: dict[str, Any] = {}
    if package_id and not run.package_id:
        run_patch["package_id"] = package_id
    if pkg_version_id and not run.package_version_id:
        run_patch["package_version_id"] = pkg_version_id
    if run_patch:
        await run_store.transition(
            db, run_id, expected_lock_version=run.lock_version,
            to_status=run.status, **run_patch,
        )
        run = await run_store.get_run(db, run_id)  # 刷新 lock_version 供后续跃迁

    nxt = _next_stage(stage)
    if nxt is None:
        # 末阶段：收口。本轮 knowledge_register 恒 deferred → run 落 degraded（诚实：语义未注册）。
        # 关键：末阶段(knowledge_register)自己无 version，pkg_version_id 为 None；绝不能把它写进
        # run（会覆盖 canonical_parse 阶段回填的真 version_id）。只在非空时才写。
        final_extra: dict[str, Any] = {}
        if pkg_version_id and not run.package_version_id:
            final_extra["package_version_id"] = pkg_version_id
        deferred = _budget_skip(reason) or status in ("skipped", "degraded")
        if deferred:
            await run_store.transition(
                db, run_id, expected_lock_version=run.lock_version,
                to_status="degraded",
                error_code=MODEL_BUDGET_DEFERRED_REASON if _budget_skip(reason) else None,
                error_message="pipeline finished with deferred/degraded stages" if deferred else None,
                **final_extra,
            )
        else:
            await run_store.transition(
                db, run_id, expected_lock_version=run.lock_version,
                to_status="completed", **final_extra,
            )
        return

    # 非末阶段：发后继（package_id/version_id 已在上面回填 run）。
    # skipped(model_budget_deferred) 也照常推进（派生物/预览对图片仍有用；末阶段才据此收口 degraded）。
    await _publish_stage(
        db, run_id=run_id, file_id=file_id, package_id=package_id,
        source_revision_id=params.get("source_revision_id"),
        source_sha256=params.get("source_sha256"),
        pipeline_version=str(params.get("pipeline_version") or "v1"),
        generation=int(params.get("generation") or 1),
        stage=nxt, owner_id=int(run.owner_id),
    )


async def _reconcile_ingest(db: AsyncSession) -> None:
    """收口漏网 run：非终态 run，其当前阶段任务已终态失败且无在跑任务 → run 落 failed。

    修补"handler 终态失败、settlement 从不被调"导致的 run 悬挂。
    """
    from sqlalchemy import text

    rows = await db.execute(
        text("""
            SELECT r.id, r.lock_version
            FROM framework_ingestion_runs r
            WHERE r.status NOT IN ('completed','degraded','failed','dead_letter','cancelled')
              AND EXISTS (
                SELECT 1 FROM framework_system_task_queues q
                WHERE q.task_type = :tt
                  AND q.document_id = r.file_id
                  AND q.status = 'failed'
              )
              AND NOT EXISTS (
                SELECT 1 FROM framework_system_task_queues q2
                WHERE q2.task_type = :tt
                  AND q2.document_id = r.file_id
                  AND q2.status IN ('pending','running')
              )
            LIMIT 200
        """),
        {"tt": INGEST_TASK_TYPE},
    )
    for run_id, lock_version in rows.all():
        await run_store.transition(
            db, run_id, expected_lock_version=int(lock_version),
            to_status="failed", error_code="stage_failed",
            error_message="stage task terminally failed; run reconciled to failed",
        )
    await db.commit()


register_task_definition(
    TaskDefinition(task_type=INGEST_TASK_TYPE, default_lane="local_preprocess", rss_estimate_mb=512)
)
register_task_handler(INGEST_TASK_TYPE, _ingest_stage_handler)
register_task_settlement_handler(INGEST_TASK_TYPE, _settle_ingest_task)
register_dispatcher_reconciler("content_ingest", _reconcile_ingest)
