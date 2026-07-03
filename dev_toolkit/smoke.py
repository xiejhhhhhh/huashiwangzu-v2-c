"""
smoke_all — 一键全回归
后端集测(probe/call_capability) + 前端UI(Playwright) + 汇总红绿矩阵.
只访问活栈(33000/5173), 不重启服务.
断言规则: 只认内层 success, 拒绝 or status==200 兜底.
"""

import asyncio
import io
import json
import os
import re
import struct
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

# ── 配置 ──────────────────────────────────────────────────────────────

BACKEND_BASE = "http://127.0.0.1:33000"
FRONTEND_BASE = "http://localhost:5173"

ACCOUNTS = {
    "admin": {"username": "何焜华", "password": "123rgE123", "user_id": 4},
    "editor": {"username": "editor", "password": "admin123", "role": "editor"},
    "viewer": {"username": "viewer", "password": "admin123", "role": "viewer"},
}

TS = int(time.time() * 1000)
results: list[dict[str, Any]] = []
_pending_deletions: list[int] = []  # 延后到所有测试结束后统一删除，避免异步 kb_pipeline 争抢

# ── 辅助 ──────────────────────────────────────────────────────────────

async def _ensure_token(role: str = "admin") -> str:
    acct = ACCOUNTS.get(role, ACCOUNTS["admin"])
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=10, trust_env=False) as client:
        resp = await client.post("/api/login", json={
            "username": acct["username"],
            "password": acct["password"],
        })
        data = resp.json()
        token = data.get("data", data).get("access_token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"Login failed {role}: {data}")
        return token

async def _upload_file(filename: str, content: bytes, mime: str, folder_id: str = "0") -> dict:
    token = await _ensure_token()
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30, trust_env=False) as client:
        resp = await client.post(
            "/api/files/upload",
            files={"file": (filename, content, mime)},
            data={"folder_id": folder_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()

async def _delete_file(file_id: int) -> bool:
    r = await probe("POST", "/api/files/delete", {"id": file_id, "type": "file"})
    return _cap_ok(r)


async def _schedule_delete(file_id: int) -> None:
    """延后删除：记录 file_id，所有测试结束后统一清理。"""
    _pending_deletions.append(file_id)


async def _flush_pending_deletions() -> int:
    """执行所有延后删除，返回删除成功数。"""
    ok = 0
    for fid in _pending_deletions:
        try:
            if await _delete_file(fid):
                ok += 1
        except Exception as e:
            print(f"  [WARN] cleanup delete file_id={fid} failed: {e}")
    _pending_deletions.clear()
    return ok


async def _await_queue_settle(baseline_pending: int = 0, timeout: int = 30) -> dict:
    """Wait for the task queue pending count to settle back to baseline (or timeout)."""
    print(f"  等待异步队列静默... (pending baseline={baseline_pending})")
    deadline = time.monotonic() + timeout
    last_state = {}
    while time.monotonic() < deadline:
        r = await probe("GET", "/api/tasks/worker/status")
        state = r.get("data", {}).get("data", r.get("data", {}))
        pend = state.get("pending", 0)
        last_state = state
        if pend <= baseline_pending:
            print(f"  队列静默: pending={pend} (基线 {baseline_pending})")
            return state
        elapsed = timeout - (deadline - time.monotonic())
        print(f"  等待中... pending={pend} (已等 {elapsed:.0f}s/{timeout}s)")
        await asyncio.sleep(2)
    print(f"  超时: pending 未归零 (最后状态 pending={last_state.get('pending', '?')})")
    return last_state


async def _read_queue_state() -> dict:
    r = await probe("GET", "/api/tasks/worker/status")
    return r.get("data", {}).get("data", r.get("data", {}))

def _cap_ok(r: dict) -> bool:
    """Check capability inner success (data.data.success), fallback to data.success."""
    data = r.get("data", {})
    inner = data.get("data")
    if isinstance(inner, dict) and "success" in inner:
        return bool(inner.get("success"))
    return bool(data.get("success"))


def _cap_payload(r: dict) -> Any:
    """Unwrap /api/modules/call and module-level unified envelopes."""
    payload: Any = r.get("data", {})
    while isinstance(payload, dict) and "data" in payload:
        next_payload = payload.get("data")
        if next_payload is payload:
            break
        payload = next_payload
    return payload


def _load_backend_env(backend_dir: str) -> None:
    env_path = os.path.join(backend_dir, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


async def _cleanup_scheduler_smoke_task(title: str) -> int:
    """Remove the scheduler task created by this smoke run."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(repo_root, "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    _load_backend_env(backend_dir)

    from app.database import AsyncSessionLocal  # noqa: PLC0415
    from app.models.system import SystemTaskQueue  # noqa: PLC0415
    from sqlalchemy import delete  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(SystemTaskQueue).where(
                SystemTaskQueue.module == "scheduler",
                SystemTaskQueue.task_type == "scheduled_agent_job",
                SystemTaskQueue.parameters.contains(title),
            )
        )
        await db.commit()
        return int(result.rowcount or 0)

def _make_png() -> bytes:
    """Minimal 2×2 red PNG."""
    width, height = 2, 2
    raw = b""
    for _ in range(height):
        raw += b"\x00"
        for _ in range(width):
            raw += b"\xff\x00\x00"
    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

async def probe(method: str, path: str, body: dict | None = None, role: str = "admin") -> dict:
    token = await _ensure_token(role)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30, trust_env=False) as client:
        resp = await client.request(method, path, json=body, headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        return {"status": resp.status_code, "data": data}

async def call_capability(module: str, action: str, params: dict | None = None, role: str = "admin") -> dict:
    token = await _ensure_token(role)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "target_module": module,
        "action": action,
        "parameters": params or {},
    }
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=60, trust_env=False) as client:
        resp = await client.post("/api/modules/call", json=body, headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        return {"status": resp.status_code, "data": data}

def add_result(scenario: str, passed: bool, notes: str = "", status: str | None = None) -> None:
    result_status = status or ("PASS" if passed else "FAIL")
    results.append({"scenario": scenario, "passed": passed, "status": result_status, "notes": notes})
    marker = {"PASS": "G", "FAIL": "R", "SKIPPED": "S"}.get(result_status, "?")
    print(f"  [{marker}] {scenario}: {notes[:120]}")


def _build_summary() -> dict[str, Any]:
    total = len(results)
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")
    failed = sum(1 for r in results if r.get("status") == "FAIL" or not r.get("passed"))
    passed = total - skipped - failed
    verdict = "FAIL" if failed else ("PASS_WITH_DEBT" if skipped else "PASS")
    return {
        "verdict": verdict,
        "clean_pass": verdict == "PASS",
        "has_debt": verdict == "PASS_WITH_DEBT",
        "counts": {"total": total, "passed": passed, "failed": failed, "skipped": skipped},
        "skipped_scenarios": [r["scenario"] for r in results if r.get("status") == "SKIPPED"],
    }


def _new_failed_delta(failed_now: int, baseline_failed: int) -> int:
    """Only count failures added by this smoke run; external cleanup is not a failure."""
    return max(0, int(failed_now or 0) - int(baseline_failed or 0))


def _no_new_queue_failures(failed_now: int, baseline_failed: int) -> bool:
    return _new_failed_delta(failed_now, baseline_failed) == 0

# ── A. 框架主链路 ──────────────────────────────────────────────────

async def test_a():
    print("\n═══════════════════ A. 框架主链路 ═══════════════════\n")

    # A1 三角色登录
    for role in ("admin", "editor", "viewer"):
        try:
            t = await _ensure_token(role)
            add_result(f"A1 登录 {role}", bool(t), "token 签发成功")
        except Exception as e:
            add_result(f"A1 登录 {role}", False, str(e))

    # A3 desktop-apps
    r = await probe("GET", "/api/desktop/apps")
    data = r.get("data", {})
    apps = data.get("data", []) if isinstance(data, dict) else data
    if isinstance(apps, list):
        add_result("A3 desktop-apps 列出", len(apps) > 0, f"{len(apps)} 个应用")
    else:
        add_result("A3 desktop-apps 列出", False, f"非数组: {str(apps)[:100]}")

    # A4 上传/下载
    try:
        up = await _upload_file(f"smoke-{TS}.txt", b"hello smoke", "text/plain")
        if up.get("success"):
            file_id = up["data"]["id"]
            add_result("A4 上传文件", True, f"file_id={file_id}")
            down = await probe("GET", f"/api/files/download/{file_id}")
            add_result("A4 下载文件", down["status"] == 200, f"status={down['status']}")
            await _schedule_delete(file_id)
        else:
            add_result("A4 上传文件", False, up.get("error", "unknown"))
    except Exception as e:
        add_result("A4 上传/下载", False, str(e))

    # A5 recycle
    try:
        up = await _upload_file(
            f"recycle-{TS}.bin",
            b"to recycle",
            "application/octet-stream",
        )
        if up.get("success"):
            fid = up["data"]["id"]
            del_r = await probe("POST", "/api/files/delete", {"id": fid, "type": "file"})
            ok = _cap_ok(del_r)
            add_result("A5 删除到回收站", ok, f"file_id={fid}")
            # 回收站文件保留用于还原测试，不由 schedule_delete 清理

            list_r = await probe("GET", "/api/recycle/list?page=1&page_size=50")
            resp = list_r.get("data", {})
            items = resp.get("data", []) if isinstance(resp, dict) else resp
            found = any(i.get("origin_id") == fid for i in items)
            add_result("A5 回收站可见", found, f"in recycle={found}")

            recycle_id = None
            for i in items:
                if i.get("origin_id") == fid:
                    recycle_id = i.get("id")
                    break
            if recycle_id:
                rest = await probe("POST", "/api/recycle/restore", {"id": recycle_id, "item_type": "file"})
                ok = _cap_ok(rest)
                add_result("A5 还原", ok, "restore OK")
                if ok:
                    await _schedule_delete(fid)
        else:
            add_result("A5 recycle", False, "upload failed")
    except Exception as e:
        add_result("A5 recycle", False, str(e))

    # A7 dashboard stats
    r = await probe("GET", "/api/dashboard/stats")
    data = r.get("data", {}).get("data", {})
    has_stats = bool(data.get("total_files") is not None)
    add_result("A7 dashboard stats", has_stats, f"{str(data)[:100]}")

# ── B. 知识库 + 解析器 ────────────────────────────────────────────

async def test_b():
    print("\n═══════════════ B. 知识库 + 解析器 ═══════════════\n")

    r = await call_capability("knowledge", "search", {"query": "test", "top_k": 3})
    ok = _cap_ok(r)
    add_result("B1 knowledge search", ok, str(r.get("data", {}))[:120])

    # text-parser via upload + call
    try:
        up = await _upload_file(f"smoke-b2-{TS}.txt", b"Hello smoke test file content", "text/plain")
        if up.get("success"):
            fid = up["data"]["id"]
            r = await call_capability("text-parser", "parse", {"file_id": fid})
            ok = _cap_ok(r)
            add_result("B2 text-parser parse", ok, str(r.get("data", {}))[:120])
            await _schedule_delete(fid)
        else:
            add_result("B2 text-parser parse", False, f"upload failed: {up.get('error','?')}")
    except Exception as e:
        add_result("B2 text-parser parse", False, str(e))

    # pdf-parser via upload + call
    try:
        raw_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 50 700 Td (hello) Tj ET\nendstream\nendobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n437\n%%EOF"
        up = await _upload_file(f"smoke-b2p-{TS}.pdf", raw_pdf, "application/pdf")
        if up.get("success"):
            fid = up["data"]["id"]
            r = await call_capability("pdf-parser", "parse", {"file_id": fid})
            ok = _cap_ok(r)
            add_result("B2 pdf-parser parse", ok, str(r.get("data", {}))[:120])
            await _schedule_delete(fid)
        else:
            add_result("B2 pdf-parser parse", False, f"upload failed: {up.get('error','?')}")
    except Exception as e:
        add_result("B2 pdf-parser parse", False, str(e))

    # image-vision describe: upload real PNG → get file_id → describe
    try:
        png = _make_png()
        up = await _upload_file(f"smoke-img-{TS}.png", png, "image/png")
        if up.get("success"):
            fid = up["data"]["id"]
            r = await call_capability("image-vision", "describe", {"file_id": fid})
            ok = _cap_ok(r)
            blocks = r.get("data", {}).get("data", {}).get("blocks", [])
            add_result("B2 image-vision describe", ok, f"blocks={len(blocks)}")
            await _schedule_delete(fid)
        else:
            add_result("B2 image-vision describe", False, f"upload failed: {up.get('error','?')}")
    except Exception as e:
        add_result("B2 image-vision describe", False, str(e))

# ── C. Agent 全链路 ───────────────────────────────────────────────

async def test_c():
    print("\n═══════════════════ C. Agent 全链路 ═══════════════════\n")

    r = await call_capability("memory", "overview_stats", {})
    ok = _cap_ok(r)
    add_result("C1 memory overview_stats", ok, str(r.get("data", {}))[:120])

    r = await call_capability("memory", "overview_stats", {})
    ok = _cap_ok(r)
    add_result("C2 memory overview_stats", ok, str(r.get("data", {}))[:120])

# ── D. 查看器 ─────────────────────────────────────────────────────

async def test_d():
    print("\n═══════════════════ D. 查看器 ═══════════════════\n")

    # D1 docs-open: POST with file_id (GET returns 405)
    try:
        up = await _upload_file(f"smoke-doc-{TS}.txt", b"hello docs open", "text/plain")
        if up.get("success"):
            fid = up["data"]["id"]
            r = await call_capability("docs-open", "open", {"file_id": fid})
            ok = _cap_ok(r)
            embed_url = r.get("data", {}).get("data", {}).get("embed_url", "")
            add_result("D1 docs-open", ok, f"has_embed={bool(embed_url)}")
            await _schedule_delete(fid)
        else:
            add_result("D1 docs-open", False, f"upload failed: {up.get('error','?')}")
    except Exception as e:
        add_result("D1 docs-open", False, str(e))

    # D2 excel-engine parse: upload real xlsx → get file_id → parse
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "col1"
        ws["B1"] = "col2"
        ws["A2"] = 1
        ws["B2"] = 2
        ws2 = wb.create_sheet("Sheet2")
        ws2["A1"] = "data"
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        xlsx_data = buf.getvalue()
        up = await _upload_file(f"smoke-xl-{TS}.xlsx", xlsx_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if up.get("success"):
            fid = up["data"]["id"]
            r = await call_capability("excel-engine", "parse", {"file_id": fid})
            ok = _cap_ok(r)
            sheets = r.get("data", {}).get("data", {}).get("all_sheets", [])
            add_result("D2 excel-engine parse", ok and len(sheets) >= 2, f"sheets={sheets}")
            await _schedule_delete(fid)
        else:
            add_result("D2 excel-engine parse", False, f"upload failed: {up.get('error','?')}")
    except Exception as e:
        add_result("D2 excel-engine parse", False, str(e))

# ── E. 工具/生成类 ─────────────────────────────────────────────────

async def test_e():
    print("\n═══════════════════ E. 工具/生成类 ═══════════════════\n")

    r = await call_capability("image-gen", "list_templates", {})
    ok = _cap_ok(r)
    templates = r.get("data", {}).get("data", {}).get("templates", [])
    add_result("E1 image-gen list_templates", ok, f"{len(templates)} templates")

    # office-gen docx: filename (not file_name) + block content
    r = await call_capability("office-gen", "docx", {
        "filename": f"smoke-{TS}",
        "content": [{"type": "heading", "text": "标题"}, {"type": "paragraph", "text": "正文"}],
    })
    ok = _cap_ok(r)
    docx_id = r.get("data", {}).get("data", {}).get("file_id")
    add_result("E2 office-gen docx", ok, f"file_id={docx_id}")
    if docx_id:
        await _schedule_delete(docx_id)

    # office-gen xlsx
    r = await call_capability("office-gen", "xlsx", {
        "filename": f"smoke-{TS}",
        "sheets": [{"name": "Sheet1", "rows": [["a", "b"], ["1", "2"]]}],
    })
    ok = _cap_ok(r)
    xlsx_id = r.get("data", {}).get("data", {}).get("file_id")
    add_result("E3 office-gen xlsx", ok, f"file_id={xlsx_id}")
    if xlsx_id:
        await _schedule_delete(xlsx_id)

    # desktop-tools
    r = await call_capability("desktop-tools", "list_files", {"folder_id": 0})
    ok = _cap_ok(r)
    add_result("E5 desktop-tools list_files", ok, str(r.get("data", {}))[:120])

    # im send: need conversation_id, create if none exists
    try:
        r = await probe("GET", "/api/im/conversations")
        convs = r.get("data", {}).get("data", [])
        if not convs:
            r2 = await probe("POST", "/api/im/messages", {"target_user_id": 3, "content": f"smoke bootstrap {TS}"})
            convs2 = _cap_payload(r2)
            conv_id = convs2.get("conversation_id") if isinstance(convs2, dict) else None
        else:
            conv_id = convs[0]["id"]
        if conv_id:
            r = await call_capability("im", "send", {"conversation_id": conv_id, "content": f"smoke test {TS}"})
            ok = _cap_ok(r)
            msg_id = r.get("data", {}).get("data", {}).get("message_id")
            add_result("E7 im send", ok, f"message_id={msg_id}")
        else:
            add_result("E7 im send", False, "could not create conversation")
    except Exception as e:
        add_result("E7 im send", False, str(e))

    scheduler_title = f"smoke-{TS}"
    scheduled_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    r = await call_capability(
        "scheduler",
        "create",
        {
            "title": scheduler_title,
            "action_description": "smoke test scheduler noop",
            "scheduled_at": scheduled_at,
        },
    )
    ok = _cap_ok(r)
    task_payload = _cap_payload(r)
    task_id = task_payload.get("id") if isinstance(task_payload, dict) else None
    cleaned = 0
    if ok and task_id:
        cancel_result = await call_capability("scheduler", "cancel", {"task_id": task_id})
        ok = _cap_ok(cancel_result)
        cleaned = await _cleanup_scheduler_smoke_task(scheduler_title)
        add_result("E8 scheduler create/cancel", ok and cleaned == 1, f"task_id={task_id}, cleaned={cleaned}")
    else:
        add_result("E8 scheduler create/cancel", ok, str(r.get("data", {}))[:120])

# ── 前端 UI 集测 ──────────────────────────────────────────────────

async def test_ui():
    print("\n═══════════════════ 前端 UI 集测 ═══════════════════\n")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(repo_root, "frontend")
    env = os.environ.copy()
    env["PLAYWRIGHT_EXTERNAL_SERVER"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            "npm", "run", "test:browser",
            cwd=frontend_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = stdout.decode() + stderr.decode()
        passed = proc.returncode == 0
        pm = re.search(r"(\d+)\s*passed", output)
        fm = re.search(r"(\d+)\s*failed", output)
        dm = re.search(r"(\d+)\s*did not run", output)
        passed_count = int(pm.group(1)) if pm else 0
        failed_count = int(fm.group(1)) if fm else 0
        did_not_run = int(dm.group(1)) if dm else 0
        add_result("UI 集测 (Playwright)", passed, f"exit={proc.returncode}, passed={passed_count}, failed={failed_count}, skipped={did_not_run}")
        if not passed:
            lines = output.split("\n")
            fail_lines = [line for line in lines if "FAIL" in line or "failed" in line.lower() or "✘" in line]
            for fl in fail_lines[-5:]:
                print(f"    {fl.strip()}")
    except asyncio.TimeoutError:
        add_result("UI 集测 (Playwright)", False, "超时(>180s)")
    except FileNotFoundError:
        add_result("UI 集测 (Playwright)", False, "npm not found")
    except Exception as e:
        add_result("UI 集测 (Playwright)", False, str(e))

# ── 健康检查 ──────────────────────────────────────────────────────────

async def health_check():
    print("\n═══════════════════ 健康检查 ═══════════════════\n")
    try:
        r = await probe("GET", "/api/health")
        h = r.get("data", {}).get("data", r.get("data", {}))
        ok = h.get("status") == "ok"
        module_errors = h.get("module_errors")
        add_result("后端 health", ok, f"db={h.get('database')}, module_errors={module_errors}")
    except Exception as e:
        add_result("后端 health", False, str(e))

    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as cli:
            r = await cli.get("http://127.0.0.1:30000/health")
            ok = r.status_code == 200
            add_result("bge-m3 嵌入服务", ok, f"status={r.status_code}")
    except Exception:
        add_result("bge-m3 嵌入服务", False, "unreachable (some features may degrade)")

# ── 主函数 ────────────────────────────────────────────────────────────

async def main():
    print("smoke_all — 一键全回归")
    print(f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"后端: {BACKEND_BASE}  前端: {FRONTEND_BASE}")

    # Capture the queue baseline before business steps create async work.
    init_state = await _read_queue_state()
    pre_failed = init_state.get("failed", 0)
    pre_pending = init_state.get("pending", 0)
    print(f"初始队列基线: failed={pre_failed}, pending={pre_pending}")

    for group_name, group in [
        ("健康检查", health_check),
        ("A. 框架主链路", test_a),
        ("B. 知识库 + 解析器", test_b),
        ("C. Agent 全链路", test_c),
        ("D. 查看器", test_d),
        ("E. 工具/生成类", test_e),
    ]:
        try:
            await group()
        except Exception as exc:
            add_result(group_name, False, f"group crashed: {exc}")
    if not os.environ.get("SMOKE_SKIP_UI"):
        try:
            await test_ui()
        except Exception as exc:
            add_result("UI 集测 (Playwright)", False, f"group crashed: {exc}")
    else:
        add_result("UI 集测 (Playwright)", True, "SMOKE_SKIP_UI=1，前端 UI 集测本轮跳过", status="SKIPPED")

    # ── 清理 & 异步队列验证 ──
    print("\n═══════════════════ 清理 + 异步队列验证 ═══════════════════\n")

    # Wait for tasks created by this smoke run to drain back to the pre-run baseline.
    await _await_queue_settle(baseline_pending=pre_pending, timeout=30)

    # 延后删除所有测试文件
    cleanup_count = len(_pending_deletions)
    deleted = await _flush_pending_deletions()
    print(f"  清理: 删除了 {deleted} 个测试文件")

    # 再等待一轮：让本次操作的队列稳定
    final = await _await_queue_settle(baseline_pending=pre_pending, timeout=30)

    # 查最终异步队列状态
    failed_now = final.get("failed", 0)
    pending_now = final.get("pending", 0)
    oldest = final.get("oldest_waiting_seconds", 0)
    new_failures = _new_failed_delta(failed_now, pre_failed)
    add_result("Z1 异步队列无意外新增失败", _no_new_queue_failures(failed_now, pre_failed),
               f"failed: {pre_failed}(业务前基线) → {failed_now}(终), 新增={new_failures}, "
               f"清理文件数={cleanup_count}")
    add_result("Z2 异步队列积压可解释", pending_now <= 5,
               f"pending={pending_now}, oldest_waiting={oldest}s")
    print("\n" + "=" * 60)
    print("  红绿矩阵")
    print("=" * 60)
    summary = _build_summary()
    counts = summary["counts"]
    total = counts["total"]
    passed = counts["passed"]
    failed = counts["failed"]
    skipped = counts["skipped"]

    print(f"\n{'场景':<40} {'结果':>6} {'备注'}")
    print("-" * 80)
    for r in results:
        status = r.get("status", "PASS" if r["passed"] else "FAIL")
        marker = {"PASS": "G", "FAIL": "R", "SKIPPED": "S"}.get(status, "?")
        print(f"{r['scenario']:<40} {marker:>6}  {r['notes'][:100]}")

    print(f"\n总计: {total} 场景, G {passed} 通过, R {failed} 失败, S {skipped} 跳过")
    print("SMOKE_JSON: " + json.dumps(summary, ensure_ascii=False))
    if failed > 0:
        print(f"{failed} 个场景失败, 请查看详情")
        sys.exit(1)
    if skipped > 0:
        print("通过但存在跳过项/债务，不是干净 PASS。")
    else:
        print("全绿!")

if __name__ == "__main__":
    asyncio.run(main())
