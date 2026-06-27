"""artifact hash → stage staleness detection.

Hash 驱动的过时检测，从 Draftpaper-loop 的模式提炼。
每个 pipeline 步骤完成后记录 artifact hash，下次 pipeline 启动前检测
上游 hash 是否变化，BFS 传播标记下游 stage 为 stale。
"""
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbPipelineStale

logger = logging.getLogger("v2.knowledge").getChild("stale")

# ── 依赖图 ────────────────────────────────────────────
# 每个 stage 依赖的上游 key
STAGE_DEPENDS_ON: dict[str, list[str]] = {
    "parse":      ["source_file"],
    "vector":     ["parse"],
    "raw":        ["source_file"],
    "fusion":     ["raw"],
    "profile":    ["fusion"],
    "graph":      ["fusion"],
    "relations":  ["profile", "graph"],
}

STAGE_ORDER = [
    "parse", "vector", "raw", "fusion",
    "profile", "graph", "relations",
]


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def record_artifact_hash(
    db: AsyncSession,
    document_id: int,
    stage: str,
    source_file_id: int | None = None,
) -> str:
    """记录某个 stage 完成时的 artifact hash。

    - ``source_file``：计算文件内容的 sha256
    - 其他 stage：基于 stage 名 + document_id + 当前时间生成唯一 hash
    返回计算出的 hash 值。
    """
    if stage == "source_file" and source_file_id:
        from app.services.file_service import get_file_storage_path
        fpath = get_file_storage_path(source_file_id)
        content_hash = _sha256_of(fpath.read_bytes()) if fpath and fpath.exists() else ""
    else:
        content_hash = _sha256_of(
            f"{stage}:{document_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        )

    r = await db.execute(
        select(KbPipelineStale).where(
            KbPipelineStale.document_id == document_id,
            KbPipelineStale.stage == stage,
        )
    )
    record = r.scalar_one_or_none()
    if record:
        record.artifact_hash = content_hash
        record.updated_at = datetime.now(timezone.utc)
    else:
        record = KbPipelineStale(
            document_id=document_id,
            stage=stage,
            artifact_hash=content_hash,
        )
        db.add(record)
    await db.commit()
    return content_hash


async def detect_stale_stages(
    db: AsyncSession,
    document_id: int,
    source_file_id: int | None = None,
) -> list[str]:
    """检测哪些 stage 因上游变化而 stale。

    返回按 STAGE_ORDER 排序的需要重新执行的 stage 列表。
    没有任何记录时返回全部 stage（首次 run）。
    """
    r = await db.execute(
        select(KbPipelineStale).where(KbPipelineStale.document_id == document_id)
    )
    records = {rec.stage: rec.artifact_hash for rec in r.scalars().all()}

    if not records:
        return STAGE_ORDER.copy()

    changed: set[str] = set()

    # 1. 检查 source_file 是否变了
    if source_file_id:
        from app.services.file_service import get_file_storage_path
        fpath = get_file_storage_path(source_file_id)
        current_hash = _sha256_of(fpath.read_bytes()) if fpath and fpath.exists() else ""
        old_hash = records.get("source_file", "")
        if current_hash != old_hash:
            changed.add("source_file")

    # 2. BFS 传播 — 任何上游改变，其直接/间接下游均为 stale
    stale_stages: set[str] = set()
    queue = list(changed)
    while queue:
        upstream = queue.pop(0)
        for stage, deps in STAGE_DEPENDS_ON.items():
            if upstream in deps and stage not in stale_stages:
                stale_stages.add(stage)
                queue.append(stage)

    return [s for s in STAGE_ORDER if s in stale_stages]


async def mark_stale(db: AsyncSession, document_id: int, stage: str) -> None:
    """手动标记某个 stage 为 stale（删除其 hash 记录）。"""
    r = await db.execute(
        select(KbPipelineStale).where(
            KbPipelineStale.document_id == document_id,
            KbPipelineStale.stage == stage,
        )
    )
    record = r.scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()
    logger.info("Marked stage %s stale for doc_id=%d", stage, document_id)


async def get_staleness_report(
    db: AsyncSession,
    document_id: int,
) -> dict:
    """返回文档各 pipeline stage 的 staleness 快照。"""
    r = await db.execute(
        select(KbPipelineStale).where(KbPipelineStale.document_id == document_id)
    )
    records = r.scalars().all()
    return {
        rec.stage: {
            "hash": rec.artifact_hash[:16] + "..." if len(rec.artifact_hash) > 16 else rec.artifact_hash,
            "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
        }
        for rec in records
    }
