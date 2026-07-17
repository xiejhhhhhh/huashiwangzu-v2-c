"""内容摄取异步编排器测试（方案07 WP2 组件 G）。

覆盖 7 条关键行为，每条都带断言：
1. source_sha256 去重 bug 已修（真字节 SHA-256，非旧 SHA256(MD5字符串)）
2. FileRevision 字节血缘（上传写 revision_no=1 / origin=user_import / current 指针）
3. 编排器幂等（同一 file 连续 kickoff：首次 created=True，再次 created=False）
4. DAG 全程推进 + §24 诚实降级（末阶段 deferred → run 落 degraded 非假绿）
5. canonical_parse 幂等（已有 version 且源 hash 未变 → idempotent，不新增版本）
6. 取消（cancel_requested → handler 落 cancelled，terminal_run=True）
7. replay（终态 run → 新 run generation+1 / replay_of_id 指向原 run / status=queued）

纯新增测试，不改任何生产代码。测试造的数据在 finally 里按 file_id 清理干净。
测试基建 1:1 照抄 test_content_package_lifecycle.py：import app.main 注册能力，
用 AsyncSessionLocal 直接拿 db session，owner_id=4（已 seed 用户）。
"""
import hashlib
import io
import uuid

import app.main  # noqa: F401 —— 导入副作用：注册各 *-parser 能力与 content_ingest_stage handler
import pytest
from app.contracts.content_hash import source_sha256_from_bytes
from app.contracts.ingestion_status import MODEL_BUDGET_DEFERRED_REASON, STAGE_DAG
from app.database import AsyncSessionLocal
from app.models.content import ContentPackage, ContentPackageVersion, ResourceRef
from app.models.content_runtime import FileRevision, IngestionRun
from app.models.file import File, FileDerivative
from app.models.system import SystemTaskQueue
from app.services.content import ingestion_run_store as run_store
from app.services.content.ingestion_orchestrator import ensure_run_and_kickoff
from app.services.content.ingestion_stages import (
    INGEST_TASK_TYPE,
    _ingest_stage_handler,
    _settle_ingest_task,
)
from app.services.content.source_revision import resolve_source_sha256
from app.services.file_upload_service import upload_file
from app.services.task_dispatcher import unpack_task_parameters
from sqlalchemy import delete, func, select

# 已 seed 的普通用户（与 test_content_package_lifecycle.py 一致）。
OWNER_ID = 4
CALLER = f"user:{OWNER_ID}"


# ── 测试工具 ────────────────────────────────────────────────────────────────

async def _upload_txt(text: str, *, ext: str = "txt") -> dict:
    """走真实上传服务落一个文本文件（含写盘 + FileRevision）。返回 upload_file 结果 dict。"""
    filename = f"ingest-{uuid.uuid4().hex}.{ext}"
    async with AsyncSessionLocal() as db:
        result = await upload_file(
            db,
            io.BytesIO(text.encode("utf-8")),
            filename,
            OWNER_ID,
        )
    return result


async def _cleanup_by_file(file_id: int | None) -> None:
    """按 file_id 把本轮造的所有派生数据删干净：run / 任务 / package+version / ref / 派生物 / revision / file。"""
    if not file_id:
        return
    async with AsyncSessionLocal() as db:
        # 摄取任务：document_id = file_id
        await db.execute(
            delete(SystemTaskQueue).where(
                SystemTaskQueue.task_type == INGEST_TASK_TYPE,
                SystemTaskQueue.document_id == file_id,
            )
        )
        # 该 file 下的 ContentPackage → 先删版本再删包
        pkg_ids = (
            await db.execute(
                select(ContentPackage.id).where(ContentPackage.source_file_id == file_id)
            )
        ).scalars().all()
        for pkg_id in pkg_ids:
            ver_ids = (
                await db.execute(
                    select(ContentPackageVersion.id).where(
                        ContentPackageVersion.package_id == pkg_id
                    )
                )
            ).scalars().all()
            for ver_id in ver_ids:
                await db.execute(delete(ResourceRef).where(ResourceRef.version_id == ver_id))
            await db.execute(
                delete(ContentPackageVersion).where(ContentPackageVersion.package_id == pkg_id)
            )
            await db.execute(delete(ContentPackage).where(ContentPackage.id == pkg_id))
        # 摄取运行账本
        await db.execute(delete(IngestionRun).where(IngestionRun.file_id == file_id))
        # 派生物 + 字节血缘 + File 本体
        await db.execute(delete(FileDerivative).where(FileDerivative.file_id == file_id))
        await db.execute(delete(FileRevision).where(FileRevision.file_id == file_id))
        await db.execute(delete(File).where(File.id == file_id))
        await db.commit()


async def _find_pending_stage_task(db, file_id: int, stage: str) -> SystemTaskQueue | None:
    """取该 file 某一阶段的待跑任务（最新一条）。手动驱动 dispatcher 用。"""
    return await db.scalar(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.task_type == INGEST_TASK_TYPE,
            SystemTaskQueue.document_id == file_id,
            SystemTaskQueue.stage_key == stage,
            SystemTaskQueue.status == "pending",
        )
        .order_by(SystemTaskQueue.id.desc())
        .limit(1)
    )


async def _drive_stage(file_id: int, stage: str) -> tuple[dict, dict]:
    """手动驱动一个阶段：查 pending 任务 → 调 handler → 调 settlement 发后继 → 标 completed。

    返回 (handler 返回的 result, 该阶段任务的展平 params)，供上层断言与幂等重跑复用。
    """
    async with AsyncSessionLocal() as db:
        task = await _find_pending_stage_task(db, file_id, stage)
        assert task is not None, f"阶段 {stage} 没有待跑任务"
        params = unpack_task_parameters(task.parameters)
        task_id = task.id

    # handler 自开 session + commit，只吃展平后的 body。
    result = await _ingest_stage_handler(params)

    # settlement 在 dispatcher 的 fenced 事务里发后继阶段；随后把当前任务落 completed，
    # 保证下一轮 _find_pending_stage_task 只命中新发的后继任务。
    async with AsyncSessionLocal() as db:
        task = await db.get(SystemTaskQueue, task_id)
        await _settle_ingest_task(db, task, result)
        task.status = "completed"
        await db.commit()
    return result, params


# ── 用例 1：source_sha256 去重 bug 已修 ────────────────────────────────────────

def test_source_sha256_is_real_byte_hash_not_md5_string_hash() -> None:
    """真字节 SHA-256：同内容稳定、异内容不同，且 != 旧假 hash SHA256(MD5十六进制串)。"""
    data_a = b"hello world content for ingestion test"
    data_b = b"a totally different payload of bytes"

    # 同内容稳定
    assert source_sha256_from_bytes(data_a) == source_sha256_from_bytes(data_a)
    # 异内容不同
    assert source_sha256_from_bytes(data_a) != source_sha256_from_bytes(data_b)
    # 值就是原始字节的 sha256
    assert source_sha256_from_bytes(data_a) == hashlib.sha256(data_a).hexdigest()

    # 回归防护：旧实现是 SHA256(MD5十六进制字符串)，新实现绝不能等于它。
    old_fake_hash = hashlib.sha256(hashlib.md5(data_a).hexdigest().encode()).hexdigest()
    assert source_sha256_from_bytes(data_a) != old_fake_hash


# ── 用例 2：上传写 FileRevision 血缘 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_records_file_revision_lineage() -> None:
    """走 upload_file 上传 → 断言写了一条 revision_no=1/origin=user_import 的 FileRevision，
    sha256 是真源字节 sha256，且 file.current_revision_id 指向它。"""
    body = f"字节血缘测试正文-{uuid.uuid4().hex}".encode("utf-8")
    file_id = None
    try:
        async with AsyncSessionLocal() as db:
            result = await upload_file(
                db, io.BytesIO(body), f"revision-{uuid.uuid4().hex}.txt", OWNER_ID,
            )
        file_id = result["id"]

        async with AsyncSessionLocal() as db:
            revisions = (
                await db.execute(
                    select(FileRevision).where(FileRevision.file_id == file_id)
                )
            ).scalars().all()
            assert len(revisions) == 1, "上传应恰好写一条 FileRevision"
            rev = revisions[0]
            assert rev.revision_no == 1
            assert rev.origin == "user_import"
            assert rev.sha256 == source_sha256_from_bytes(body)

            file = await db.get(File, file_id)
            assert file is not None
            assert file.current_revision_id == rev.id
    finally:
        await _cleanup_by_file(file_id)


# ── 用例 3：编排器幂等 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_run_and_kickoff_is_idempotent() -> None:
    """同一 file 连续 kickoff 两次：首次 created=True，再次 created=False（不重复建 run）。"""
    file_id = None
    try:
        upload = await _upload_txt("幂等 kickoff 测试正文")
        file_id = upload["id"]

        first = await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")
        second = await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")

        assert first["created"] is True
        assert second["created"] is False
        assert second["run_id"] == first["run_id"]

        # 只应有一条 run
        async with AsyncSessionLocal() as db:
            run_count = await db.scalar(
                select(func.count(IngestionRun.id)).where(IngestionRun.file_id == file_id)
            )
            assert int(run_count) == 1
    finally:
        await _cleanup_by_file(file_id)


# ── 用例 4：DAG 全程推进 + §24 诚实降级 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_full_dag_advances_and_settles_degraded_honestly() -> None:
    """从 package_ensure 一路手动驱动到 knowledge_register：
    - DAG 顺序正确
    - knowledge_register 返回 skipped / model_budget_deferred
    - run 终态 = degraded 且 error_code = model_budget_deferred（不是 completed 假绿）
    - run.package_version_id 被正确回填（非 None）
    """
    file_id = None
    try:
        upload = await _upload_txt("# 标题\n\nDAG 全程推进测试正文。\n\n第二段内容。")
        file_id = upload["id"]

        kickoff = await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")
        assert kickoff["created"] is True
        run_id = kickoff["run_id"]

        # 按 DAG 固定顺序逐阶段驱动，记录实际命中的阶段顺序。
        observed_stages: list[str] = []
        last_result: dict = {}
        for stage in STAGE_DAG:
            result, _params = await _drive_stage(file_id, stage)
            observed_stages.append(result["stage"])
            last_result = result

        # DAG 顺序正确
        assert observed_stages == list(STAGE_DAG)

        # 末阶段 knowledge_register：诚实标 skipped + model_budget_deferred
        assert last_result["stage"] == "knowledge_register"
        assert last_result["status"] == "skipped"
        assert last_result["reason"] == MODEL_BUDGET_DEFERRED_REASON

        # run 终态 = degraded（非 completed 假绿），error_code = model_budget_deferred，
        # 且 canonical_parse 回填的 package_version_id 没被末阶段覆盖成 None。
        async with AsyncSessionLocal() as db:
            run = await run_store.get_run(db, run_id)
            assert run is not None
            assert run.status == "degraded"
            assert run.error_code == MODEL_BUDGET_DEFERRED_REASON
            assert run.package_version_id is not None
            assert run.package_id is not None
    finally:
        await _cleanup_by_file(file_id)


# ── 用例 5：canonical_parse 幂等 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_canonical_parse_is_idempotent_when_source_unchanged() -> None:
    """run 已有 package_version_id 且 source_sha256 未变时，再跑 canonical_parse
    返回 idempotent=True，且不新增 ContentPackageVersion（版本数不变）。"""
    file_id = None
    try:
        upload = await _upload_txt("canonical_parse 幂等测试正文，内容保持不变。")
        file_id = upload["id"]

        await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")

        # 先把 package_ensure、canonical_parse 跑一遍，拿到 canonical_parse 的展平 params。
        await _drive_stage(file_id, "package_ensure")
        parse_result, parse_params = await _drive_stage(file_id, "canonical_parse")
        assert parse_result.get("package_version_id") is not None

        # 记录当前该 package 的版本数
        async with AsyncSessionLocal() as db:
            pkg_id = await db.scalar(
                select(ContentPackage.id).where(ContentPackage.source_file_id == file_id)
            )
            before = await db.scalar(
                select(func.count(ContentPackageVersion.id)).where(
                    ContentPackageVersion.package_id == pkg_id
                )
            )

        # 用同一份 params 再跑一次 canonical_parse handler（源 hash 未变）。
        again = await _ingest_stage_handler(parse_params)
        assert again.get("idempotent") is True

        async with AsyncSessionLocal() as db:
            after = await db.scalar(
                select(func.count(ContentPackageVersion.id)).where(
                    ContentPackageVersion.package_id == pkg_id
                )
            )
        assert int(after) == int(before), "canonical_parse 幂等重跑不应新增版本"
    finally:
        await _cleanup_by_file(file_id)


# ── 用例 6：取消 ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_requested_makes_handler_land_cancelled() -> None:
    """request_cancel 后，handler 开头检测到 cancel_requested → run 落 cancelled、
    返回 terminal_run=True。"""
    file_id = None
    try:
        upload = await _upload_txt("取消测试正文")
        file_id = upload["id"]

        kickoff = await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")
        run_id = kickoff["run_id"]

        # 打取消标记（独立事务提交）
        async with AsyncSessionLocal() as db:
            ok = await run_store.request_cancel(db, run_id, reason="pytest_cancel")
            await db.commit()
            assert ok is True

        # 取首阶段 pending 任务的 params，直接调 handler
        async with AsyncSessionLocal() as db:
            task = await _find_pending_stage_task(db, file_id, "package_ensure")
            assert task is not None
            params = unpack_task_parameters(task.parameters)
        result = await _ingest_stage_handler(params)

        assert result["status"] == "skipped"
        assert result["reason"] == "cancelled"
        assert result["terminal_run"] is True

        async with AsyncSessionLocal() as db:
            run = await run_store.get_run(db, run_id)
            assert run is not None
            assert run.status == "cancelled"
    finally:
        await _cleanup_by_file(file_id)


# ── 用例 7：replay ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_replay_builds_next_generation_run() -> None:
    """终态 run 调 create_replay → 新 run generation+1、replay_of_id 指向原 run、status=queued。"""
    file_id = None
    try:
        upload = await _upload_txt("replay 测试正文")
        file_id = upload["id"]

        kickoff = await ensure_run_and_kickoff(file_id, CALLER, trigger="upload")
        origin_run_id = kickoff["run_id"]

        # 把原 run 推到终态（degraded），再建重放
        async with AsyncSessionLocal() as db:
            origin = await run_store.get_run(db, origin_run_id)
            await run_store.mark_degraded(
                db, origin, error_code=MODEL_BUDGET_DEFERRED_REASON,
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            origin = await run_store.get_run(db, origin_run_id)
            assert origin.status == "degraded"
            replay = await run_store.create_replay(db, origin, requested_by=OWNER_ID)
            await db.commit()
            replay_id = replay.id

        async with AsyncSessionLocal() as db:
            origin = await run_store.get_run(db, origin_run_id)
            replay = await run_store.get_run(db, replay_id)
            assert replay is not None
            assert replay.generation == origin.generation + 1
            assert replay.replay_of_id == origin_run_id
            assert replay.status == "queued"
    finally:
        await _cleanup_by_file(file_id)
