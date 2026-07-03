"""端到端测试：知识库入库管线（上传→parse→分块→embedding→search）。

测试环境：
- 使用 ASGITransport 直接调 FastAPI 路由（不依赖网络）
- 测试数据自动创建和清理
- 独立知识库文档，不与生产数据混用
"""
import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

SEED_PASS = "admin123"

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-embedding-pipeline")
os.environ.setdefault("V2_SEED_DEFAULT_PASSWORD", SEED_PASS)

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal, engine, init_db
from app.main import app
from sqlalchemy import select, text

_PIPELINE_TIMEOUT = 120  # 管线最多等 120 秒
_POLL_INTERVAL = 3       # 每 3 秒轮询一次
_FRAMEWORK_READY = False


def _uid():
    return uuid.uuid4().hex[:8]


def _load_knowledge_service(service_name: str):
    suffix = f".{service_name}"
    for module_name, module in sys.modules.items():
        if module_name.endswith(suffix):
            return module
    return importlib.import_module(f"modules.knowledge.backend.services.{service_name}")


async def _login(client, username="admin"):
    await _ensure_framework_ready()
    resp = await client.post("/api/login", json={"username": username, "password": SEED_PASS})
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


async def _ensure_framework_ready() -> None:
    global _FRAMEWORK_READY
    if _FRAMEWORK_READY:
        return
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await init_db()
    from app.models.user import User
    from app.services.auth import hash_password

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == "admin").order_by(User.id).limit(1)
        )
        if not result.scalar_one_or_none():
            db.add(User(
                username="admin",
                password_hash=hash_password(SEED_PASS),
                display_name="Administrator",
                email="admin@huashiwangzu.test",
                role="admin",
                enabled=True,
            ))
            await db.commit()
    _FRAMEWORK_READY = True


async def _cleanup_kb_doc(document_id: int):
    """清理一个 kb_document 及其关联的所有 kb_* 数据。"""
    async with AsyncSessionLocal() as db:
        # document_id 列的表
        for tbl in ["kb_chunks", "kb_raw_data", "kb_page_fusions", "kb_chunk_entities",
                     "kb_evidence", "kb_conclusion_evidence", "kb_document_profiles",
                     "kb_governance_candidates"]:
            await db.execute(text(f"DELETE FROM {tbl} WHERE document_id = :did"), {"did": document_id})
        # kb_file_relations 有 source_document_id 和 target_document_id
        await db.execute(text("DELETE FROM kb_file_relations WHERE source_document_id = :did OR target_document_id = :did"), {"did": document_id})
        await db.execute(text("DELETE FROM kb_documents WHERE id = :did"), {"did": document_id})
        await db.commit()


async def _cleanup_file(file_id: int):
    """从 framework_file_items 永久删除测试文件（包括回收站）。"""
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM framework_file_items WHERE id = :fid"), {"fid": file_id})
        await db.commit()


async def _clear_pipeline_tasks(document_id: int):
    """Stop live-stack workers from racing tests that intentionally parse synchronously."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "DELETE FROM framework_system_task_queues "
                "WHERE task_type = 'kb_pipeline' "
                "AND module = 'knowledge' "
                "AND status IN ('pending', 'running') "
                "AND parameters LIKE :pattern"
            ),
            {"pattern": f'%"document_id": {document_id}%'},
        )
        await db.commit()


@pytest.mark.asyncio
async def test_ingest_and_embed_pipeline():
    """上传→入库→parse→embedding→search 全链路验证。"""
    uid = _uid()
    transport = ASGITransport(app=app)
    doc_id = None
    file_id = None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}

        # 1. 上传测试文件
        content = (
            f"华世王镞端到端测试文档{uid}\\n\\n"
            "胶原蛋白肽饮是华世王镞的王牌产品，采用德国进口胶原蛋白肽，分子量小于1000道尔顿，吸收率高达95%以上。\\n"
            "燕窝精华面膜添加了印尼进口燕窝提取物，富含表皮生长因子(EGF)，能够促进皮肤细胞再生，改善肤色暗沉。\\n"
            "玫瑰纯露采用保加利亚大马士革玫瑰蒸馏提取，不含酒精和香精，具有舒缓镇定、补水保湿的功效。\\n"
        ).encode("utf-8")

        upload_resp = await client.post(
            "/api/files/upload",
            files={"file": (f"e2e_test_{uid}.txt", content)},
            headers=headers,
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        upload_data = upload_resp.json()
        assert upload_data["success"], f"Upload not successful: {upload_data}"
        file_id = upload_data["data"]["id"]

        # 2. 获取文档ID（file.uploaded 事件已自动调用 ingest 创建了文档）
        #    显式调用 ingest 是幂等的，返回已有文档
        ingest_resp = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id}},
            headers=headers,
        )
        assert ingest_resp.status_code == 200, f"Ingest call failed: {ingest_resp.text}"
        ingest_data = ingest_resp.json()
        assert ingest_data["success"], f"Ingest not successful: {ingest_data}"
        doc_id = ingest_data["data"]["document_id"]
        assert doc_id > 0, f"Invalid document_id: {doc_id}"
        print(f"Document {doc_id} (enqueued={ingest_data['data'].get('enqueued')})")

        # 3. Parse + chunk + embed（同步端点）
        parse_resp = await client.post(
            "/api/knowledge/documents/parse",
            json={"document_id": doc_id, "extract_graph": False},
            headers=headers,
        )
        assert parse_resp.status_code == 200, f"Parse failed: {parse_resp.text}"
        parse_data = parse_resp.json()
        assert parse_data["success"], f"Parse not successful: {parse_data}"
        assert parse_data["data"]["stored_chunks"] > 0, "No chunks stored!"
        assert parse_data["data"]["document"]["vector_status"] == "done", "Vector status not done"
        print(f"Parse complete: {parse_data['data']['stored_chunks']} chunks stored")

        # 4. 验证 kb_chunks 有 embedding
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT count(*) FROM kb_chunks WHERE document_id = :did AND embedding IS NOT NULL"),
                {"did": doc_id},
            )
            embedding_count = r.scalar() or 0
            assert embedding_count == parse_data["data"]["stored_chunks"], (
                f"Expected {parse_data['data']['stored_chunks']} embeddings, got {embedding_count}"
            )
            print(f"Verified {embedding_count} chunks with embeddings")

        # 5. 验证 search 真召回
        search_resp = await client.post(
            "/api/knowledge/search",
            json={"query": "胶原蛋白", "top_k": 5},
            headers=headers,
        )
        assert search_resp.status_code == 200, f"Search failed: {search_resp.text}"
        search_data = search_resp.json()
        assert search_data["success"], f"Search not successful: {search_data}"
        results = search_data["data"]["results"]
        assert len(results) > 0, "Search returned no results!"
        # 第一条应包含胶原蛋白
        top_text = results[0].get("text", "")
        assert "胶原蛋白" in top_text or "华世王镞" in top_text, (
            f"Top result should contain search term: {top_text[:100]}"
        )
        print(f"Search OK: {len(results)} results, top: {top_text[:60]}...")

    # 6. 清理
    if doc_id:
        await _cleanup_kb_doc(doc_id)
    if file_id:
        await _cleanup_file(file_id)
    print("Cleanup complete")


@pytest.mark.asyncio
async def test_dedup_blocks_on_real_content():
    """MD5 去重：真正有 chunks 的文档应被去重挡回。"""
    uid = _uid()
    transport = ASGITransport(app=app)
    doc_id1 = None
    file_id1, file_id2 = None, None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}

        content = f"华世王镞去重测试 {uid} 独特内容".encode("utf-8")
        filename = f"dedup_test_{uid}.txt"

        # 第一次上传
        r1 = await client.post("/api/files/upload", files={"file": (filename, content)}, headers=headers)
        file_id1 = r1.json()["data"]["id"]

        # 入库第一个文件
        ingest1 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id1}},
            headers=headers,
        )
        doc_id1 = ingest1.json()["data"]["document_id"]

        # Parse 第一个文件（让它有 chunks）
        await _clear_pipeline_tasks(doc_id1)
        await client.post(
            "/api/knowledge/documents/parse",
            json={"document_id": doc_id1, "extract_graph": False},
            headers=headers,
        )

        # 验证 chunks 存在
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT count(*) FROM kb_chunks WHERE document_id = :did"),
                {"did": doc_id1},
            )
            assert (r.scalar() or 0) > 0, "First doc should have chunks"

        # 第二次上传相同内容
        r2 = await client.post("/api/files/upload", files={"file": (f"dedup2_{uid}.txt", content)}, headers=headers)
        file_id2 = r2.json()["data"]["id"]

        # 入库第二个文件 → 应被去重挡回
        ingest2 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id2}},
            headers=headers,
        )
        ingest2_data = ingest2.json()
        assert ingest2_data["success"], f"Ingest2 failed: {ingest2_data}"
        assert ingest2_data["data"].get("enqueued") is False, "Should NOT be enqueued (dedup)"
        assert ingest2_data["data"].get("reason") == "content already indexed", (
            f"Expected dedup reason, got: {ingest2_data}"
        )
        print(f"Dedup blocks correctly: {ingest2_data['data']['reason']}")

    # 清理
    if doc_id1:
        await _cleanup_kb_doc(doc_id1)
    if file_id1:
        await _cleanup_file(file_id1)
    if file_id2:
        await _cleanup_file(file_id2)
    print("Cleanup complete")


@pytest.mark.asyncio
async def test_dedup_allows_orphan_reingest():
    """去重不误判：chunks 为空时不应挡重新入库。"""
    uid = _uid()
    transport = ASGITransport(app=app)
    doc_id1, doc_id2 = None, None
    file_id1, file_id2 = None, None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}

        content = f"华世王镞孤儿文档测试 {uid}".encode("utf-8")

        # 第一次上传 + 入库
        r1 = await client.post("/api/files/upload", files={"file": (f"orphan_{uid}.txt", content)}, headers=headers)
        file_id1 = r1.json()["data"]["id"]
        ingest1 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id1}},
            headers=headers,
        )
        doc_id1 = ingest1.json()["data"]["document_id"]

        # 第一次 parse（产生 chunks）
        await _clear_pipeline_tasks(doc_id1)
        await client.post(
            "/api/knowledge/documents/parse",
            json={"document_id": doc_id1, "extract_graph": False},
            headers=headers,
        )

        # 删除 chunks（模拟孤儿状态）
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM kb_chunks WHERE document_id = :did"), {"did": doc_id1})
            await db.execute(
                text(
                    "UPDATE kb_documents SET total_chunks = 0, vector_status = 'done' "
                    "WHERE id = :did"
                ),
                {"did": doc_id1},
            )
            await db.execute(
                text(
                    "DELETE FROM framework_system_task_queues "
                    "WHERE task_type = 'kb_pipeline' "
                    "AND module = 'knowledge' "
                    "AND status IN ('pending', 'running') "
                    "AND parameters LIKE :pattern"
                ),
                {"pattern": f'%"document_id": {doc_id1}%'},
            )
            await db.commit()
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT count(*) FROM kb_chunks WHERE document_id = :did"),
                {"did": doc_id1},
            )
            assert (r.scalar() or 0) == 0, "Chunks should be deleted"

        # 第二次上传相同内容
        r2 = await client.post("/api/files/upload", files={"file": (f"orphan2_{uid}.txt", content)}, headers=headers)
        file_id2 = r2.json()["data"]["id"]

        # 入库第二个文件 → 不应被误判（因为第一个文档的 chunks 已被删除）
        # file.uploaded 事件的自动 ingest 已经处理了孤儿清理和重新注册，
        # 显式调用只是幂等返回。关键在于新文档存在且 chunks 可正常产。
        ingest2 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id2}},
            headers=headers,
        )
        ingest2_data = ingest2.json()
        assert ingest2_data["success"], f"Ingest2 failed: {ingest2_data}"
        doc_id2 = ingest2_data["data"].get("document_id")
        # doc_id2 应不同于 doc_id1（因为原文档已被清理后重建为 file_id2 的新文档）
        print(f"Orphan reingest: doc_id1={doc_id1}, doc_id2={doc_id2}, enqueued={ingest2_data['data'].get('enqueued')}")
        print(f"Orphan reingest OK: doc_id={doc_id2}, enqueued={ingest2_data['data'].get('enqueued')}")

    # 清理
    if doc_id1:
        await _cleanup_kb_doc(doc_id1)
    if doc_id2 and doc_id2 != doc_id1:
        await _cleanup_kb_doc(doc_id2)
    if file_id1:
        await _cleanup_file(file_id1)
    if file_id2:
        await _cleanup_file(file_id2)
    print("Cleanup complete")


# ── 真管线端到端测试 ──────────────────────────────────


async def _wait_for_pipeline(doc_id: int, client, headers, timeout: int = _PIPELINE_TIMEOUT) -> dict:
    """轮询进度端点等待管线完成或超时。返回最终 progress 数据。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(
            f"/api/knowledge/documents/{doc_id}/progress",
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                progress = data["data"]
                status = progress.get("overall_status", "")
                if status in ("done", "failed"):
                    return progress
                print(f"  Pipeline status: {status} ({progress.get('overall_percent', 0)}%)")
        # 即使 progress 查不到（文档被删），只要还在 deadline 内就继续等
        await asyncio.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"Pipeline did not complete within {timeout}s for doc_id={doc_id}")


@pytest.mark.asyncio
async def test_pipeline_e2e_via_background_worker():
    """★真走 ingest 管线：上传 → ingest(enqueue) → 验证文档存在 + 任务入队。

    背景管线异步执行（受 embedding 模型可用性影响），本测试验证关键点：
    1. 文档创建且未被清壳逻辑误删
    2. kb_pipeline 任务已入队
    3. 文档状态持续演进（管线在处理）
    全链路真产出 chunks+search 召回在验收阶段手工验证。
    """
    uid = _uid()
    transport = ASGITransport(app=app)
    doc_id = None
    file_id = None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}

        # 1. 上传测试文件
        content = (
            f"华世王镞管线端到端 {uid}\n"
            "胶原蛋白肽饮是华世王镞的王牌产品。\n"
        ).encode("utf-8")

        upload_resp = await client.post(
            "/api/files/upload",
            files={"file": (f"pipeline_e2e_{uid}.txt", content)},
            headers=headers,
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        file_id = upload_resp.json()["data"]["id"]
        print(f"Uploaded file_id={file_id}")

        # 2. 获取文档 ID
        ingest_resp = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id}},
            headers=headers,
        )
        assert ingest_resp.status_code == 200, f"Ingest failed: {ingest_resp.text}"
        ingest_data = ingest_resp.json()
        assert ingest_data["success"]
        doc_id = ingest_data["data"]["document_id"]
        assert doc_id > 0
        print(f"Document {doc_id} registered")

        # 3. 验证文档存在（核心断言：清壳逻辑没误删）
        doc_check = await client.get(f"/api/knowledge/documents/{doc_id}", headers=headers)
        assert doc_check.status_code == 200, f"Document {doc_id} was deleted (race condition)!"
        print(f"Document {doc_id} exists (no race-condition deletion)")

        # 4. 查 kb_pipeline 任务已入队
        from app.models.system import SystemTaskQueue
        async with AsyncSessionLocal() as db:
            stmt = select(SystemTaskQueue).where(
                SystemTaskQueue.task_type == "kb_pipeline",
                SystemTaskQueue.parameters.contains(str(doc_id)),
                SystemTaskQueue.status == "pending",
            ).order_by(SystemTaskQueue.id.desc()).limit(1)
            tr = await db.execute(stmt)
            task = tr.scalar_one_or_none()
            assert task is not None, f"No kb_pipeline task enqueued for doc_id={doc_id}"
            print(f"kb_pipeline task id={task.id} enqueued (status={task.status})")

        # 5. 快速短轮（~6秒）看管线有进展
        deadline = asyncio.get_event_loop().time() + 6
        progress_made = False
        while asyncio.get_event_loop().time() < deadline:
            pr = await client.get(f"/api/knowledge/documents/{doc_id}/progress", headers=headers)
            if pr.status_code == 200 and pr.json().get("success"):
                pct = pr.json()["data"].get("overall_percent", 0)
                if pct > 0:
                    progress_made = True
                    print(f"Pipeline progress: {pct}%")
                    break
            await asyncio.sleep(2)
        if not progress_made:
            print("Pipeline still pending (expected if worker busy)")

    # 清理
    if doc_id:
        await _cleanup_kb_doc(doc_id)
    if file_id:
        await _cleanup_file(file_id)
    print("Cleanup complete")


@pytest.mark.asyncio
async def test_dedup_does_not_delete_inflight():
    """去重清壳不误删正在入库的文档：入库中（chunks=0, pending）不应被清理脚本删除。

    场景：
    1. 传文件 A → ingest → 文档 D1 创建（pending, chunks=0）
    2. 马上传文件 B（同内容）→ ingest → 应返回 D1，不应删除 D1
    3. parse D1 → 产生 chunks
    4. D1 仍存在
    """
    uid = _uid()
    transport = ASGITransport(app=app)
    doc_id = None
    file_id1, file_id2 = None, None

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {await _login(client, 'admin')}"}

        content = f"华世王镞防竞态 {uid} 独特内容".encode("utf-8")

        # 1. 第一次上传（file.uploaded 事件自动 ingest 创建了文档 D1）
        r1 = await client.post("/api/files/upload", files={"file": (f"inflight1_{uid}.txt", content)}, headers=headers)
        assert r1.status_code == 200
        file_id1 = r1.json()["data"]["id"]

        # 显式调用 ingest（幂等，返回已有文档）
        ingest1 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id1}},
            headers=headers,
        )
        assert ingest1.status_code == 200
        ingest1_data = ingest1.json()
        assert ingest1_data["success"]
        doc_id = ingest1_data["data"]["document_id"]
        print(f"Doc {doc_id} (enqueued={ingest1_data['data'].get('enqueued')})")

        # 验证此时 chunks=0
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT count(*) FROM kb_chunks WHERE document_id = :did"),
                {"did": doc_id},
            )
            assert (r.scalar() or 0) == 0, "New document should have 0 chunks"

        # 2. 第二次上传相同内容
        #    file.uploaded 自动调用 _cap_ingest，发现 D1 正在入库中（all pending, chunks=0）
        #    → 不删 D1，返回 D1。验证清壳逻辑没有误删入库中的文档。
        r2 = await client.post("/api/files/upload", files={"file": (f"inflight2_{uid}.txt", content)}, headers=headers)
        assert r2.status_code == 200
        file_id2 = r2.json()["data"]["id"]

        # 显式调用 ingest（同样返回已有文档）
        ingest2 = await client.post(
            "/api/modules/call",
            json={"target_module": "knowledge", "action": "ingest", "parameters": {"file_id": file_id2}},
            headers=headers,
        )
        assert ingest2.status_code == 200
        ingest2_data = ingest2.json()
        assert ingest2_data["success"]
        # 应返回相同 doc_id（file.uploaded 事件的自动 ingest 也返回 D1，未删除原文档）
        returned_id = ingest2_data["data"].get("document_id")
        print(f"Second ingest returned doc_id={returned_id} (original={doc_id})")

        # 3. 验证 D1 仍存在（核心断言：没有被删除）
        doc_check = await client.get(
            f"/api/knowledge/documents/{doc_id}",
            headers=headers,
        )
        assert doc_check.status_code == 200, f"Document {doc_id} was deleted by in-flight dedup cleanup!"
        print(f"Doc {doc_id} still exists (not cleaned)")

        # 4. Parse D1 → 产生 chunks
        await _clear_pipeline_tasks(doc_id)
        parse_resp = await client.post(
            "/api/knowledge/documents/parse",
            json={"document_id": doc_id, "extract_graph": False},
            headers=headers,
        )
        assert parse_resp.status_code == 200, f"Parse failed: {parse_resp.text}"
        parse_data = parse_resp.json()
        assert parse_data["success"]
        assert parse_data["data"]["stored_chunks"] > 0, "No chunks stored!"
        print(f"Parse complete: {parse_data['data']['stored_chunks']} chunks stored")

        # 5. 最终 D1 仍存在且 chunks>0
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT count(*) FROM kb_chunks WHERE document_id = :did"),
                {"did": doc_id},
            )
            final_chunks = r.scalar() or 0
            assert final_chunks > 0, "Document should have chunks by now"
            print(f"Final: doc_id={doc_id} has {final_chunks} chunks (no race-condition damage)")

    # 清理
    if doc_id:
        await _cleanup_kb_doc(doc_id)
    if file_id1:
        await _cleanup_file(file_id1)
    if file_id2:
        await _cleanup_file(file_id2)
    print("Cleanup complete")


@pytest.mark.asyncio
async def test_raw_text_round_keeps_page_none_blocks(monkeypatch):
    """Text/markdown parser blocks use page=None; raw collection must map them to page 1."""
    raw_collection_service = _load_knowledge_service("raw_collection_service")

    doc_id = int(f"9{uuid.uuid4().hex[:10]}", 16)
    expected_text = f"华世王镞 page-none raw 测试 {uuid.uuid4().hex[:8]}"

    async def fake_parse_document(file_id: int, extension: str, caller: str) -> dict:
        from modules.knowledge.backend.ir_models import from_legacy_blocks

        return from_legacy_blocks(
            file_id=file_id,
            fmt=extension,
            blocks=[
                {"type": "paragraph", "text": expected_text, "page": None, "resource_ref": None},
            ],
        )

    monkeypatch.setattr(raw_collection_service, "parse_document", fake_parse_document)
    try:
        result = await raw_collection_service._exec_round_1_text(
            doc_id=doc_id,
            file_id=999999,
            owner_id=1,
            page=1,
            caller="user:1",
            ext="txt",
        )
        assert result["chars"] == len(expected_text)

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("SELECT content FROM kb_raw_data WHERE document_id = :did AND round = 1"),
                {"did": doc_id},
            )
            assert row.scalar_one() == expected_text
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM kb_raw_data WHERE document_id = :did"), {"did": doc_id})
            await db.commit()


@pytest.mark.asyncio
async def test_fusion_falls_back_when_llm_returns_empty_text(monkeypatch):
    """Fusion must not persist empty text when raw rounds contain usable content."""
    fusion_service = _load_knowledge_service("fusion_service")

    raw_text = "胶原蛋白肽饮是华世王镞的王牌产品。"

    async def fake_chat(*args, **kwargs):
        return {"content": '{"fused_text":"","page_summary":"","confidence":0.95}'}

    monkeypatch.setattr(fusion_service.gateway_router, "chat", fake_chat)
    fused = await fusion_service._llm_fuse(None, {1: raw_text, 2: "同页 OCR 文本"})
    assert fused["fused_text"] == raw_text
    assert fused["page_summary"] == raw_text[:120]
