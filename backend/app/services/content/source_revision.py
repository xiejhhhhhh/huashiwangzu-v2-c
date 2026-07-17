"""File 字节血缘(FileRevision)写入与真 sha256 解析(方案07 §19.3-C / §19.4)。

铁律:
- 每次 File 字节变化(上传 / 替换 / 投影)只新增一条 Revision,不原地改。
- source hash 一律用原始字节 SHA-256(见 content_hash.source_sha256_*),
  禁止旧实现 SHA256(MD5字符串)。
- current_revision_id 是 File 的"当前字节"指针,回填期由本模块统一维护。

本模块只做纯字节血缘,不触发任何模型调用(§24)。
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.contracts.content_hash import source_sha256_from_path
from app.contracts.ingestion_status import FileRevisionOrigin
from app.models.content_runtime import FileRevision
from app.models.file import File

logger = logging.getLogger("v2.content").getChild("source_revision")

_UPLOAD_ROOT = Path(get_settings().UPLOAD_DIR).resolve()


def _abs_storage_path(storage_path: str) -> Path:
    """storage_path 是相对 UPLOAD_ROOT 的内容寻址路径,拼成绝对路径。"""
    return _UPLOAD_ROOT / storage_path


async def record_file_revision(
    db: AsyncSession,
    file: File,
    *,
    sha256: str | None,
    origin: FileRevisionOrigin,
    created_by: int = 0,
    set_current: bool = True,
) -> FileRevision:
    """为 File 新增一条字节血缘,并(默认)把 current_revision_id 指过去。

    调用方负责在同一事务里已经 flush 出 file.id。本函数只 add + flush Revision,
    不 commit —— 由上层上传/替换事务统一提交,保证 File 记录与其 Revision 原子落库。
    """
    if not file.id:
        await db.flush()

    # revision_no 单调递增:取该 file 现有最大值 + 1(首条 = 1)
    max_no = await db.scalar(
        select(func.coalesce(func.max(FileRevision.revision_no), 0)).where(
            FileRevision.file_id == file.id
        )
    )
    revision = FileRevision(
        file_id=file.id,
        revision_no=int(max_no or 0) + 1,
        storage_path=file.storage_path or "",
        size=int(file.size or 0),
        sha256=sha256,
        mime_type=file.mime_type or "application/octet-stream",
        origin=origin,
        created_by=created_by,
    )
    db.add(revision)
    await db.flush()

    if set_current:
        file.current_revision_id = revision.id

    logger.info(
        "[日志-字节血缘] file_id=%s revision_no=%s origin=%s sha256=%s",
        file.id, revision.revision_no, origin, (sha256 or "")[:12],
    )
    return revision


async def resolve_source_sha256(db: AsyncSession, file: File) -> str | None:
    """解析 File 当前字节的真 sha256(只读,不写库)。

    优先读已算好的 current_revision.sha256(上传/替换时算过,零重复开销);
    没有 Revision 的历史文件,回退到对 storage_path 流式重算一次。
    算不出返回 None,由调用方决定降级策略。
    """
    if file.current_revision_id:
        rev = await db.get(FileRevision, file.current_revision_id)
        if rev and rev.sha256:
            return rev.sha256

    # 历史文件无 Revision:找该 file 最新一条 Revision 的 sha256
    latest = await db.scalar(
        select(FileRevision.sha256)
        .where(FileRevision.file_id == file.id, FileRevision.sha256.isnot(None))
        .order_by(FileRevision.revision_no.desc())
        .limit(1)
    )
    if latest:
        return latest

    # 彻底没有血缘:对磁盘字节流式重算一次(不落库,回填交给专门迁移)
    if file.storage_path:
        abs_path = _abs_storage_path(file.storage_path)
        try:
            if abs_path.exists():
                return source_sha256_from_path(str(abs_path))
        except OSError as exc:
            logger.warning(
                "[日志-字节血缘] file_id=%s 重算 sha256 失败: %s", file.id, exc
            )
    return None
