"""
项目工具台 MCP Server
自包含 MCP 服务器, stdio 传输, 暴露项目开发工具.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

try:
    from dev_toolkit.agent_board_tools import handle_tool as agent_board_handle_tool
    from dev_toolkit.agent_board_tools import handles_tool as agent_board_handles_tool
    from dev_toolkit.agent_board_tools import tool_definitions as agent_board_tool_definitions
    from dev_toolkit.code_tools import handle_tool as code_handle_tool
    from dev_toolkit.code_tools import handles_tool as code_handles_tool
    from dev_toolkit.code_tools import lint as code_lint
    from dev_toolkit.code_tools import normalize_pytest_targets as _normalize_pytest_targets_raw
    from dev_toolkit.code_tools import resolve_repo_path as _resolve_repo_path_raw
    from dev_toolkit.code_tools import run_test as code_run_test
    from dev_toolkit.code_tools import tool_definitions as code_tool_definitions
    from dev_toolkit.contract_tools import handle_tool as contract_handle_tool
    from dev_toolkit.contract_tools import handles_tool as contract_handles_tool
    from dev_toolkit.contract_tools import tool_definitions as contract_tool_definitions
    from dev_toolkit.core_tools import CoreToolContext
    from dev_toolkit.core_tools import handle_tool as core_handle_tool
    from dev_toolkit.core_tools import handles_tool as core_handles_tool
    from dev_toolkit.core_tools import tool_definitions as core_tool_definitions
    from dev_toolkit.db_reverse_tools import handle_tool as db_reverse_handle_tool
    from dev_toolkit.db_reverse_tools import handles_tool as db_reverse_handles_tool
    from dev_toolkit.db_reverse_tools import tool_definitions as db_reverse_tool_definitions
    from dev_toolkit.edit_tools import handle_tool as edit_handle_tool
    from dev_toolkit.edit_tools import handles_tool as edit_handles_tool
    from dev_toolkit.edit_tools import tool_definitions as edit_tool_definitions
    from dev_toolkit.insight_tools import handle_tool as insight_handle_tool
    from dev_toolkit.insight_tools import handles_tool as insight_handles_tool
    from dev_toolkit.insight_tools import tool_definitions as insight_tool_definitions
    from dev_toolkit.mailbox_tools import handle_tool as mailbox_handle_tool
    from dev_toolkit.mailbox_tools import handles_tool as mailbox_handles_tool
    from dev_toolkit.mailbox_tools import outbox_dir as mailbox_outbox_dir
    from dev_toolkit.mailbox_tools import tool_definitions as mailbox_tool_definitions
    from dev_toolkit.mcp_entry import SERVER_NAME, SERVER_VERSION
    from dev_toolkit.memory_tools import handle_tool as memory_handle_tool
    from dev_toolkit.memory_tools import handles_tool as memory_handles_tool
    from dev_toolkit.memory_tools import list_memories
    from dev_toolkit.memory_tools import tool_definitions as memory_tool_definitions
    from dev_toolkit.memory_tools import update_index as memory_update_index
    from dev_toolkit.opencode_pty_tools import handle_tool as opencode_pty_handle_tool
    from dev_toolkit.opencode_pty_tools import handles_tool as opencode_pty_handles_tool
    from dev_toolkit.opencode_pty_tools import tool_definitions as opencode_pty_tool_definitions
    from dev_toolkit.opencode_tools import handle_tool as opencode_handle_tool
    from dev_toolkit.opencode_tools import handles_tool as opencode_handles_tool
    from dev_toolkit.opencode_tools import tool_definitions as opencode_tool_definitions
    from dev_toolkit.quick_fix import QuickFixError
    from dev_toolkit.release_response import build_release_gate_response as build_release_gate_payload
    from dev_toolkit.response_shaping import ResponseShapeOptions, dumps_response
    from dev_toolkit.sql_guard import check_sql_readonly, readonly_psql_env
    from dev_toolkit.tool_usage_tools import handle_tool as tool_usage_handle_tool
    from dev_toolkit.tool_usage_tools import handles_tool as tool_usage_handles_tool
    from dev_toolkit.tool_usage_tools import record_tool_usage
    from dev_toolkit.tool_usage_tools import tool_definitions as tool_usage_tool_definitions
    from dev_toolkit.worktree_tools import git_status_summary, worktree_guard
    from dev_toolkit.worktree_tools import handle_tool as worktree_handle_tool
    from dev_toolkit.worktree_tools import handles_tool as worktree_handles_tool
    from dev_toolkit.worktree_tools import tool_definitions as worktree_tool_definitions
except ModuleNotFoundError:
    from agent_board_tools import handle_tool as agent_board_handle_tool
    from agent_board_tools import handles_tool as agent_board_handles_tool
    from agent_board_tools import tool_definitions as agent_board_tool_definitions
    from code_tools import handle_tool as code_handle_tool
    from code_tools import handles_tool as code_handles_tool
    from code_tools import lint as code_lint
    from code_tools import normalize_pytest_targets as _normalize_pytest_targets_raw
    from code_tools import resolve_repo_path as _resolve_repo_path_raw
    from code_tools import run_test as code_run_test
    from code_tools import tool_definitions as code_tool_definitions
    from contract_tools import handle_tool as contract_handle_tool
    from contract_tools import handles_tool as contract_handles_tool
    from contract_tools import tool_definitions as contract_tool_definitions
    from core_tools import CoreToolContext
    from core_tools import handle_tool as core_handle_tool
    from core_tools import handles_tool as core_handles_tool
    from core_tools import tool_definitions as core_tool_definitions
    from db_reverse_tools import handle_tool as db_reverse_handle_tool
    from db_reverse_tools import handles_tool as db_reverse_handles_tool
    from db_reverse_tools import tool_definitions as db_reverse_tool_definitions
    from edit_tools import handle_tool as edit_handle_tool
    from edit_tools import handles_tool as edit_handles_tool
    from edit_tools import tool_definitions as edit_tool_definitions
    from insight_tools import handle_tool as insight_handle_tool
    from insight_tools import handles_tool as insight_handles_tool
    from insight_tools import tool_definitions as insight_tool_definitions
    from mailbox_tools import handle_tool as mailbox_handle_tool
    from mailbox_tools import handles_tool as mailbox_handles_tool
    from mailbox_tools import outbox_dir as mailbox_outbox_dir
    from mailbox_tools import tool_definitions as mailbox_tool_definitions
    from mcp_entry import SERVER_NAME, SERVER_VERSION
    from memory_tools import handle_tool as memory_handle_tool
    from memory_tools import handles_tool as memory_handles_tool
    from memory_tools import list_memories
    from memory_tools import tool_definitions as memory_tool_definitions
    from memory_tools import update_index as memory_update_index
    from opencode_pty_tools import handle_tool as opencode_pty_handle_tool
    from opencode_pty_tools import handles_tool as opencode_pty_handles_tool
    from opencode_pty_tools import tool_definitions as opencode_pty_tool_definitions
    from opencode_tools import handle_tool as opencode_handle_tool
    from opencode_tools import handles_tool as opencode_handles_tool
    from opencode_tools import tool_definitions as opencode_tool_definitions
    from quick_fix import QuickFixError
    from release_response import build_release_gate_response as build_release_gate_payload
    from response_shaping import ResponseShapeOptions, dumps_response
    from sql_guard import check_sql_readonly, readonly_psql_env
    from tool_usage_tools import handle_tool as tool_usage_handle_tool
    from tool_usage_tools import handles_tool as tool_usage_handles_tool
    from tool_usage_tools import record_tool_usage
    from tool_usage_tools import tool_definitions as tool_usage_tool_definitions
    from worktree_tools import git_status_summary, worktree_guard
    from worktree_tools import handle_tool as worktree_handle_tool
    from worktree_tools import handles_tool as worktree_handles_tool
    from worktree_tools import tool_definitions as worktree_tool_definitions

# ── 配置 ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "dev_toolkit" / "config.json"

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)

BACKEND_BASE = CONFIG["backend_base_url"]
BGE_M3_URL = CONFIG["bge_m3_url"]
ACCOUNTS = CONFIG["accounts"]
MEMORY_DIR = REPO_ROOT / CONFIG["memory_dir"]
EMBEDDING_CACHE_PATH = REPO_ROOT / CONFIG["embedding_cache"]
LOG_DIR = REPO_ROOT / CONFIG["log_dir"]
DB_DSN = CONFIG["db_dsn"]
UPLOADS_DIR = REPO_ROOT / "backend" / "data" / "uploads"
TOOL_USAGE_PATH = LOG_DIR / "tool_usage_stats.json"
_OUTPUT_TAIL_LIMIT = 8000
MEMORY_NOISE_PATTERN = re.compile(
    r"(e2e-|smoke-|test-|test_|kb_test|kb-test|ui-e2e|audit-test|renamed-audit-test|docs-open验收|event_test|e2e_test|sample|to_del|验收|smoke)",
    re.IGNORECASE,
)


def _normalize_pytest_targets(target: str) -> list[str]:
    return _normalize_pytest_targets_raw(REPO_ROOT, target)


def _resolve_repo_path(path: str) -> Path:
    return _resolve_repo_path_raw(REPO_ROOT, path)


def _is_knowledge_noise_name(filename: str) -> bool:
    """Check if a filename looks like a test/smoke/validation artifact."""
    return bool(MEMORY_NOISE_PATTERN.search(filename))


# ── 通用 helper ───────────────────────────────────────────────────────


def _tail_text(text: str, limit: int = _OUTPUT_TAIL_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


async def _run_command_json(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
) -> dict[str, Any]:
    started = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return {
            "success": False,
            "timeout": True,
            "timeout_seconds": timeout,
            "command": cmd,
            "cwd": str(cwd),
            "duration_seconds": round(time.time() - started, 3),
            "stdout": "",
            "stderr": "",
        }
    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": cmd,
        "cwd": str(cwd),
        "duration_seconds": round(time.time() - started, 3),
        "stdout": out,
        "stderr": err,
        "stdout_tail": _tail_text(out),
        "stderr_tail": _tail_text(err),
    }


# 确保记忆目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
EMBEDDING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── Token 缓存 ────────────────────────────────────────────────────────

_token_cache: dict[str, dict[str, Any]] = {}  # role -> {"token": str, "expires_at": float}

async def _ensure_token(role: str = "admin", *, force_refresh: bool = False) -> str:
    if role not in ACCOUNTS:
        role = "admin"
    now = time.time()
    cached = _token_cache.get(role)
    if not force_refresh and cached and cached["expires_at"] > now + 60:
        return cached["token"]
    acct = ACCOUNTS[role]
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=10, trust_env=False) as client:
        resp = await client.post("/api/login", json={
            "username": acct["username"],
            "password": acct["password"],
        })
        data = resp.json()
        token = data.get("data", data).get("access_token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"登录失败 {role}: {data}")
        _token_cache[role] = {"token": token, "expires_at": now + 3600}
        return token


async def _ensure_live_token(role: str = "admin") -> str:
    token = await _ensure_token(role, force_refresh=True)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=10, trust_env=False) as client:
        resp = await client.get("/api/current-user", headers=headers)
        if resp.status_code == 200:
            return token
    token = await _ensure_token(role, force_refresh=True)
    _token_cache.pop(role, None)
    return token

# ── SQL 只读执行器 ──────────────────────────────────────────────────

def _check_sql_readonly(query: str) -> None:
    check_sql_readonly(query)

async def _execute_sql(query: str) -> list[dict[str, Any]]:
    _check_sql_readonly(query)
    # 用 psql 执行(也可以用 asyncpg, 但 psql 更通用无需额外包)
    dsn = DB_DSN
    cmd = ["psql", dsn, "-t", "-A", "-F", "\t", "--no-align", "--field-separator=|", "-c", query]
    env = readonly_psql_env(os.environ)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"SQL 执行失败: {stderr.decode()}")
    lines = stdout.decode().strip().split("\n")
    if not lines or (len(lines) == 1 and not lines[0].strip()):
        return []
    # 简化返回: 每行一条记录
    result = []
    for line in lines[:200]:
        parts = line.split("|")
        result.append({f"col{i}": p for i, p in enumerate(parts)})
    return result

# ── 日志工具 ─────────────────────────────────────────────────────────

_LOG_MAP = {
    "backend": "uvicorn.out",
    "auth": "auth.log",
    "agent": "agent.log",
    "codemap": "codemap.log",
    "knowledge": None,  # 尝试 modules/knowledge.log
    "docs-open": "docs-open.log",
    "image-gen": "image-gen.log",
    "file-transfer": "file_transfer.log",
    "gateway": "gateway.log",
    "im": "im.log",
    "command-safety": "command_safety.log",
}

def _tail_file(path: Path, lines: int) -> str:
    if not path.exists():
        return f"[文件不存在] {path}"
    # 用 subprocess tail 命令
    try:
        result = subprocess.run(
            ["tail", f"-n{lines}", str(path)],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return "[错误] tail 超时"
    except Exception as e:
        return f"[错误] {e}"


def _clear_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text("", encoding="utf-8")
    tmp_path.replace(path)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        try:
            return str(path.relative_to(LOG_DIR))
        except ValueError:
            return str(path)


def _resolve_log_paths(module: str, *, all_logs: bool = False) -> list[Path]:
    if all_logs:
        return sorted(
            path for path in LOG_DIR.rglob("*")
            if path.is_file() and path.suffix in {".log", ".out"}
        )

    module_key = module.strip().lower()
    mapped = _LOG_MAP.get(module_key)
    if mapped is None:
        candidates = [
            LOG_DIR / f"modules/{module_key}.log",
            LOG_DIR / f"modules/{module_key.replace('-', '_')}.log",
            LOG_DIR / f"modules/{module_key.replace('_', '-')}.log",
        ]
        return [path for path in candidates if path.exists()]
    return [LOG_DIR / mapped]


def _clear_log(module: str = "backend", all_logs: bool = False, keep_state: bool = True) -> dict[str, Any]:
    cleared: list[str] = []
    missing: list[str] = []

    for path in _resolve_log_paths(module, all_logs=all_logs):
        if path.exists() and path.is_file():
            _clear_file(path)
            cleared.append(_display_path(path))
        else:
            missing.append(_display_path(path))

    preserved = []
    if keep_state:
        preserved = [
            _display_path(LOG_DIR / ".backend.port"),
            _display_path(LOG_DIR / ".watchdog.pid"),
        ]

    return {
        "success": True,
        "module": module,
        "all": all_logs,
        "keep_state": keep_state,
        "cleared": cleared,
        "missing": missing,
        "preserved": preserved,
    }


def _cleanup_knowledge_noise() -> dict[str, Any]:
    removed_uploads: list[str] = []
    removed_memory: list[str] = []

    if UPLOADS_DIR.exists():
        for path in UPLOADS_DIR.rglob("*"):
            if not path.is_file():
                continue
            if _is_knowledge_noise_name(path.name):
                try:
                    path.unlink()
                    removed_uploads.append(str(path.relative_to(REPO_ROOT)))
                except FileNotFoundError:
                    pass

    if MEMORY_DIR.exists():
        for path in MEMORY_DIR.glob("*.md"):
            if path.name.startswith("_"):
                continue
            if _is_knowledge_noise_name(path.name):
                try:
                    path.unlink()
                    removed_memory.append(str(path.relative_to(REPO_ROOT)))
                except FileNotFoundError:
                    pass

    try:
        if removed_memory:
            memory_update_index(REPO_ROOT, MEMORY_DIR)
    except Exception:
        pass

    return {
        "removed_uploads": removed_uploads,
        "removed_memory": removed_memory,
        "upload_count": len(removed_uploads),
        "memory_count": len(removed_memory),
    }


def _knowledge_noise_report() -> dict[str, Any]:
    upload_counts = Counter()
    upload_samples: list[str] = []
    if UPLOADS_DIR.exists():
        # collect suspicious names from all upload files
        for path in UPLOADS_DIR.rglob("*"):
            if not path.is_file():
                continue
            if _is_knowledge_noise_name(path.name):
                upload_counts[path.suffix.lower() or "(no_ext)"] += 1
                if len(upload_samples) < 40:
                    upload_samples.append(str(path.relative_to(REPO_ROOT)))

    memory_samples: list[str] = []
    if MEMORY_DIR.exists():
        for path in MEMORY_DIR.glob("*.md"):
            if path.name.startswith("_"):
                continue
            if _is_knowledge_noise_name(path.name):
                if len(memory_samples) < 40:
                    memory_samples.append(str(path.relative_to(REPO_ROOT)))

    return {
        "upload_noise_count": sum(upload_counts.values()),
        "upload_noise_by_suffix": dict(upload_counts),
        "upload_noise_samples": upload_samples,
        "memory_noise_count": len(memory_samples),
        "memory_noise_samples": memory_samples,
        "hint": "这些名字看起来像测试/烟雾/验收产物，可用 knowledge_cleanup_noise 清理。",
    }


async def _run_psql(sql: str, timeout: int = 60) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "psql",
        DB_DSN,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode(), stderr.decode()


async def _fetch_table_count(table: str) -> int:
    code, out, err = await _run_psql(f"SELECT count(*) FROM {table};", timeout=30)
    if code != 0:
        raise RuntimeError(err.strip() or f"count query failed for {table}")
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return 0


async def _workspace_audit() -> dict[str, Any]:
    tables = [
        "framework_file_items",
        "framework_file_folders",
        "framework_file_shares",
        "framework_desktop_states",
        "framework_file_recycle_items",
        "framework_file_json_packages",
        "framework_file_json_versions",
        "framework_file_json_patches",
        "framework_file_json_tasks",
        "kb_catalogs",
        "kb_documents",
        "kb_chunks",
        "kb_page_fusions",
        "kb_raw_data",
        "kb_entity_dictionary",
        "kb_entity_aliases",
        "kb_disambiguation",
        "kb_graph_nodes",
        "kb_graph_edges",
        "kb_chunk_entities",
        "kb_evidence",
        "kb_conclusion_evidence",
        "kb_entity_merge_log",
        "kb_governance_candidates",
        "kb_document_profiles",
        "kb_file_relations",
    ]
    rows = []
    for table in tables:
        try:
            rows.append({"table": table, "count": await _fetch_table_count(table)})
        except Exception as exc:
            rows.append({"table": table, "error": str(exc)})

    upload_count = 0
    if UPLOADS_DIR.exists():
        upload_count = sum(1 for p in UPLOADS_DIR.rglob("*") if p.is_file())

    noise_report = _knowledge_noise_report()
    return {
        "uploads_files": upload_count,
        "table_counts": rows,
        "noise_report": noise_report,
    }


async def _workspace_reset(confirm: str, scope: str = "all") -> dict[str, Any]:
    if confirm != "RESET":
        return {"error": "confirm must be RESET", "rejected": True}

    scope = scope.lower().strip()
    if scope not in {"all", "desktop", "knowledge", "files"}:
        return {"error": "scope must be one of all/desktop/knowledge/files", "rejected": True}

    deleted_files: list[str] = []
    if scope in {"all", "files", "knowledge"} and UPLOADS_DIR.exists():
        for path in UPLOADS_DIR.rglob("*"):
            if not path.is_file():
                continue
            try:
                path.unlink()
                deleted_files.append(str(path.relative_to(REPO_ROOT)))
            except FileNotFoundError:
                continue

    table_groups = {
        "files": [
            "framework_file_shares",
            "framework_file_recycle_items",
            "framework_file_json_packages",
            "framework_file_json_versions",
            "framework_file_json_patches",
            "framework_file_json_tasks",
            "framework_file_items",
            "framework_file_folders",
            "framework_desktop_states",
        ],
        "knowledge": [
            "kb_conclusion_evidence",
            "kb_evidence",
            "kb_chunk_entities",
            "kb_graph_edges",
            "kb_graph_nodes",
            "kb_disambiguation",
            "kb_entity_aliases",
            "kb_entity_dictionary",
            "kb_raw_data",
            "kb_page_fusions",
            "kb_document_profiles",
            "kb_governance_candidates",
            "kb_chunks",
            "kb_documents",
            "kb_catalogs",
            "kb_entity_merge_log",
            "kb_file_relations",
        ],
    }
    tables_to_truncate: list[str] = []
    if scope == "all":
        tables_to_truncate = table_groups["knowledge"] + table_groups["files"]
    else:
        tables_to_truncate = table_groups[scope]

    if tables_to_truncate:
        sql = "TRUNCATE TABLE " + ", ".join(tables_to_truncate) + " RESTART IDENTITY CASCADE;"
        code, out, err = await _run_psql(sql, timeout=60)
        if code != 0:
            return {"error": err.strip() or out.strip() or "reset failed", "rejected": True}

    return {
        "success": True,
        "scope": scope,
        "truncated_tables": tables_to_truncate,
        "deleted_files": deleted_files[:200],
        "deleted_file_count": len(deleted_files),
    }





# ──────────────────── 工具: _restart_backend ───────────────────────


async def _restart_backend() -> dict[str, Any]:
    """重启后端服务并验证健康检查。"""
    import signal

    result = {"status": "ok", "restarted": False, "port": 0, "health": ""}

    # 1. 找 uvicorn 进程并杀掉
    killed = 0
    try:
        out = subprocess.run(
            ["pgrep", "-f", "uvicorn app.main:app"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in out.stdout.strip().split("\n"):
            pid_str = pid_str.strip()
            if pid_str:
                try:
                    os.kill(int(pid_str), signal.SIGTERM)
                    killed += 1
                except OSError:
                    pass
    except Exception:
        pass

    result["killed"] = killed

    # 2. 等待端口释放
    for _ in range(5):
        try:
            subprocess.run(
                ["lsof", "-ti:33000"], capture_output=True, timeout=3,
            )
            await asyncio.sleep(1.0)
        except Exception:
            break

    # 3. 启动后端
    start_script = REPO_ROOT / "scripts" / "start_backend.sh"
    if not start_script.exists():
        result["error"] = f"start_backend.sh not found at {start_script}"
        return result

    proc = await asyncio.create_subprocess_exec(
        "zsh", str(start_script),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    stdout, stderr = await proc.communicate()
    output = (stdout + stderr).decode("utf-8", errors="replace")

    # 4. 等待健康检查
    port = 33000
    port_file = REPO_ROOT / "backend" / "logs" / ".backend.port"
    if port_file.exists():
        try:
            port = int(port_file.read_text().strip())
        except (ValueError, OSError):
            port = 33000

    health = "unknown"
    for _ in range(15):
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as c:
                r = await c.get("/api/health")
                health = r.text[:300]
                if r.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(1.0)

    result["restarted"] = True
    result["port"] = port
    result["health"] = health
    result["output"] = output[-500:]
    return result


# ──────────────────── 工具: _verify_tool_args ──────────────────────


async def _verify_tool_args() -> dict[str, Any]:
    """存入 tool_call 事件并投影, 验证 arguments 类型。"""

    result: dict[str, Any] = {"ok": False, "arguments_type": "unknown", "arguments": None}

    async def _inner():
        from app.database import AsyncSessionLocal
        from sqlalchemy import select

        from modules.agent.backend.engine.event_store import project_to_messages, record_event
        from modules.agent.backend.models import AgentConversation

        async with AsyncSessionLocal() as db:
            conv = await db.scalar(
                select(AgentConversation).order_by(AgentConversation.id.desc())
            )
            if not conv:
                result["error"] = "no conversation found"
                return
            cid = conv.id
            await record_event(db, cid, "assistant_msg", {"content": "mcp-test"}, "_mcp_verify")
            await record_event(
                db, cid, "tool_call",
                {"id": "call_mcp", "name": "skill_list", "arguments": {"category": "web-tools"}},
                "_mcp_verify",
            )
            await record_event(
                db, cid, "tool_result",
                {"tool_call_id": "call_mcp", "name": "skill_list", "result": {"ok": True}},
                "_mcp_verify",
            )
            msgs = await project_to_messages(db, cid)
            for m in msgs:
                if m.get("tool_calls"):
                    tc = m["tool_calls"][0]
                    result["arguments_type"] = type(tc["function"]["arguments"]).__name__
                    result["arguments"] = tc["function"]["arguments"]
                    result["ok"] = isinstance(tc["function"]["arguments"], str)
                    result["expected"] = "str"
                    break

    try:
        await _inner()
    except Exception as e:
        result["error"] = str(e)

    return result


# ──────────────────── 工具: _snap_diff ────────────────────────────


async def _snap_diff() -> dict[str, Any]:
    """输出未提交文件的 diff 快照。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--short",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        out, _ = await proc.communicate()
        files = [line.strip() for line in out.decode().split("\n") if line.strip()]
        return {"files": files, "count": len(files)}
    except Exception as e:
        return {"files": [], "count": 0, "error": str(e)}

_CODEGRAPH_CLI = str(Path.home() / ".npm-global" / "bin" / "codegraph")
_RUFF_CLI = str(REPO_ROOT / "backend" / ".venv" / "bin" / "ruff")
_BACKEND_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"


def _project_python() -> str:
    return str(_BACKEND_PYTHON if _BACKEND_PYTHON.exists() else Path(sys.executable))


def _extract_prefixed_json(output: str, prefix: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text.startswith(prefix):
            continue
        try:
            data = json.loads(text[len(prefix):].strip())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


async def _smoke_all(skip_ui: bool = False) -> str:
    """Run dev_toolkit/smoke.py and return its complete red/green matrix output."""
    env = os.environ.copy()
    if skip_ui:
        env["SMOKE_SKIP_UI"] = "1"
    started = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            _project_python(),
            str(REPO_ROOT / "dev_toolkit" / "smoke.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=360)
    except asyncio.TimeoutError:
        return json.dumps(
            {"success": False, "clean_pass": False, "verdict": "TIMEOUT", "timeout": True, "timeout_seconds": 360},
            ensure_ascii=False,
            indent=2,
        )
    output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
    summary = _extract_prefixed_json(output, "SMOKE_JSON:")
    verdict = summary.get("verdict") if summary else ("PASS" if proc.returncode == 0 else "FAIL")
    if not isinstance(verdict, str) or not verdict:
        verdict = "PASS" if proc.returncode == 0 else "FAIL"
    clean_pass = proc.returncode == 0 and verdict == "PASS"
    return json.dumps(
        {
            "success": clean_pass,
            "completed": proc.returncode == 0,
            "clean_pass": clean_pass,
            "verdict": verdict,
            "has_debt": verdict == "PASS_WITH_DEBT",
            "returncode": proc.returncode,
            "skip_ui": skip_ui,
            "duration_seconds": round(time.time() - started, 3),
            "summary": summary,
            "output": output,
            "output_tail": _tail_text(output, 20000),
        },
        ensure_ascii=False,
        indent=2,
    )

# ──────────────────── 工具: release_gate ──────────────────────────

def _build_release_gate_response(
    output: str,
    returncode: int,
    skip_ui: bool,
    duration_seconds: float,
) -> dict[str, Any]:
    return build_release_gate_payload(output, returncode, skip_ui, duration_seconds)


async def _release_gate(skip_ui: bool = False) -> str:
    """Run dev_toolkit/release_gate.py and return its verdict."""
    env = os.environ.copy()
    if skip_ui:
        env["RELEASE_GATE_SKIP_UI"] = "1"
    started = time.time()
    try:
        cmd = [_project_python(), str(REPO_ROOT / "dev_toolkit" / "release_gate.py")]
        if skip_ui:
            cmd.append("--skip-ui")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
    except asyncio.TimeoutError:
        return json.dumps(
            {"success": False, "clean_pass": False, "release_safe": False, "verdict": "BLOCKER", "timeout": True, "timeout_seconds": 600},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        _build_release_gate_response(
            output=output,
            returncode=proc.returncode,
            skip_ui=skip_ui,
            duration_seconds=time.time() - started,
        ),
        ensure_ascii=False,
        indent=2,
    )


async def _module_sandbox_matrix(check: bool = False) -> str:
    """Run dev_toolkit/module_sandbox_matrix.py and return results."""
    started = time.time()
    cmd = [_project_python(), str(REPO_ROOT / "dev_toolkit" / "module_sandbox_matrix.py")]
    if check:
        cmd.append("--check")
    cmd.append("--json")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode(errors="replace")
    except asyncio.TimeoutError:
        return json.dumps({"success": False, "timeout": True, "timeout_seconds": 300}, ensure_ascii=False, indent=2)
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = {"raw_output": output}
    return json.dumps(
        {
            "success": proc.returncode == 0 or proc.returncode == 1,
            "returncode": proc.returncode,
            "check": check,
            "duration_seconds": round(time.time() - started, 3),
            "data": data,
        },
        ensure_ascii=False,
        indent=2,
    )


# ──────────────────── 工具 12: routes ────────────────────────────────

async def _routes(filter_str: str = "") -> str:
    """从 openapi.json 查准后端端点."""
    url = f"{BACKEND_BASE}/openapi.json"
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return json.dumps({"error": f"openapi.json 返回 {resp.status_code}"}, ensure_ascii=False)
            spec = resp.json()
    except Exception as e:
        return json.dumps({"error": f"获取 openapi.json 失败: {e}"}, ensure_ascii=False)

    paths = spec.get("paths", {})
    results = []
    f = filter_str.lower()
    for path, methods in paths.items():
        if f and f not in path.lower():
            continue
        for method, detail in methods.items():
            params = []
            for p in (detail.get("parameters") or []):
                params.append({"name": p.get("name"), "in": p.get("in"), "required": p.get("required", False)})
            req_body = detail.get("requestBody")
            if req_body:
                content = req_body.get("content", {})
                for media_type, media_detail in content.items():
                    schema = media_detail.get("schema", {})
                    params.append({"name": "(body)", "in": "body", "schema": schema})
            results.append({
                "method": method.upper(),
                "path": path,
                "summary": detail.get("summary", ""),
                "params": params,
            })
    results.sort(key=lambda r: r["path"])
    return json.dumps(results, ensure_ascii=False, indent=2)

# ──────────────────── 工具 13: capabilities ─────────────────────────

async def _capabilities(module: str = "") -> str:
    """扫描模块 manifest.json 的 public_actions."""
    modules_dir = REPO_ROOT / "modules"
    if not modules_dir.exists():
        return json.dumps({"error": "modules 目录不存在"}, ensure_ascii=False)
    results = []
    for manifest_path in sorted(modules_dir.glob("*/manifest.json")):
        mod_key = manifest_path.parent.name
        if module and mod_key != module:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            results.append({"module": mod_key, "error": str(e)})
            continue
        public_actions = manifest.get("public_actions", {})
        if isinstance(public_actions, dict):
            for action, action_detail in public_actions.items():
                params = []
                for p in action_detail.get("parameters", []):
                    params.append({"name": p.get("name", ""), "type": p.get("type", "")})
                results.append({
                    "module": mod_key,
                    "action": action,
                    "params": params,
                    "min_role": action_detail.get("min_role", ""),
                })
        elif isinstance(public_actions, list):
            for item in public_actions:
                if isinstance(item, str):
                    results.append({"module": mod_key, "action": item, "params": [], "min_role": ""})
                elif isinstance(item, dict):
                    results.append({
                        "module": mod_key,
                        "action": item.get("action", item.get("name", "")),
                        "params": item.get("parameters", []),
                        "min_role": item.get("min_role", ""),
                    })
    return json.dumps(results, ensure_ascii=False, indent=2)

# ──────────────────── 工具 14: db_schema ────────────────────────────

async def _db_schema(table: str = "") -> str:
    """查数据库表结构."""
    if not table:
        # 列出所有表名, 按前缀分组
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        rows = await _execute_sql(query)
        tables = [list(r.values())[0] for r in rows]
        # 按前缀分组
        grouped: dict[str, list[str]] = {}
        for t in tables:
            prefix = t.split("_")[0] if "_" in t else "(other)"
            grouped.setdefault(prefix, []).append(t)
        return json.dumps(grouped, ensure_ascii=False, indent=2)
    else:
        query = f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '{table.replace("'", "''")}'
            ORDER BY ordinal_position
        """
        rows = await _execute_sql(query)
        columns = []
        for r in rows:
            vals = list(r.values())
            columns.append({
                "column": vals[0],
                "type": vals[1],
                "nullable": vals[2],
                "default": vals[3],
            })
        return json.dumps(columns, ensure_ascii=False, indent=2)

async def _start_frontend() -> str:
    """Start the frontend dev server from the frontend directory."""
    frontend_dir = REPO_ROOT / "frontend"
    proc = await asyncio.create_subprocess_exec(
        "npm", "run", "dev",
        cwd=str(frontend_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.sleep(1)
    stdout = ""
    stderr = ""
    if proc.stdout is not None:
        try:
            stdout = (await asyncio.wait_for(proc.stdout.read(), timeout=0.5)).decode(errors="replace")
        except Exception:
            stdout = ""
    if proc.stderr is not None:
        try:
            stderr = (await asyncio.wait_for(proc.stderr.read(), timeout=0.5)).decode(errors="replace")
        except Exception:
            stderr = ""
    return json.dumps({
        "success": proc.returncode is None,
        "pid": proc.pid,
        "command": "cd frontend && npm run dev",
        "stdout": stdout,
        "stderr": stderr,
    }, ensure_ascii=False, indent=2)

async def _sanity_check() -> str:
    """Run a focused repo sanity check for common regression signals."""
    results: list[dict[str, Any]] = []

    frontend_port = await _run_command_json(
        ["lsof", "-nP", "-iTCP:5173", "-sTCP:LISTEN"],
        cwd=REPO_ROOT,
        timeout=10,
    )
    results.append({
        "check": "frontend_port_5173",
        "success": frontend_port.get("success", False),
        "details": frontend_port.get("stdout_tail") or frontend_port.get("stderr_tail") or "not listening",
    })

    backend_health = await _probe("GET", "/api/health")
    results.append({
        "check": "backend_health",
        "success": '"status": "ok"' in backend_health,
        "details": backend_health,
    })

    backend_tail = await _tail_log("backend", 80)
    import_failures = [
        line for line in backend_tail.splitlines()
        if "Failed to load module router" in line or "MODEL_PROFILES" in line
    ]
    results.append({
        "check": "backend_module_imports",
        "success": not import_failures,
        "details": import_failures[:20],
    })

    knowledge_tail = await _tail_log("knowledge", 80)
    teardown_risks = [
        line for line in knowledge_tail.splitlines()
        if "renderer.dispose is not a function" in line or "Unhandled error during execution of unmounted hook" in line
    ]
    results.append({
        "check": "knowledge_teardown",
        "success": not teardown_risks,
        "details": teardown_risks[:20],
    })

    payload = {
        "success": all(item["success"] for item in results),
        "results": results,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

async def _finish_task(
    summary: str,
    agent: str = "",
    lint_paths: str = "",
    test_targets: str = "",
    module_key: str = "",
    allowed_prefixes: str = "",
    baseline_paths: str = "",
    baseline_status_json: str = "",
    verification_summary: str = "",
    risk_note: str = "",
) -> str:
    """收工检查: 汇总工作区 + 边界检查 + 可选 lint/test + 风险评估 + 留痕模板。"""
    report: dict[str, Any] = {
        "success": True,
        "summary": summary,
        "agent": agent,
        "git": await git_status_summary(_run_command_json, REPO_ROOT),
        "boundary_check": {},
        "lint": [],
        "tests": [],
        "verification_summary": verification_summary or "(未填写验证结果)",
        "risk_note": risk_note or "(未填写)",
        "memory_write_template": {
            "agent": agent,
            "type": "task",
            "title": summary[:80] or "task summary",
            "body": "# 改了什么\n\n# 验证了什么\n\n# 是否还有残留风险\n\n# 关联 commit",
            "tags": "",
        },
        "mcp_feedback_template": {
            "agent": agent,
            "task_summary": summary[:160] or "task summary",
            "rating": 4,
            "smoothness": "本次 MCP 是否顺畅？一句话说明",
            "tools_used": "列出本次关键 MCP 工具",
            "friction": "遇到的卡点；没有写无",
            "missing_tools": "缺少的工具/能力；没有写无",
            "upgrade_suggestions": "下次可升级建议；没有写无",
            "remove_or_merge_suggestions": "不好用/可合并/可移除工具；没有写无",
            "notes": "",
        },
        "mailbox_delivery_template": {
            "task_name": summary[:100] or "task summary",
            "summary": "做了什么、关键结果、关键设计",
            "changed_files": "逐行列出本次新增/修改/删除文件",
            "verification_results": verification_summary or "贴验收命令和原始输出",
            "risks": risk_note or "无",
            "status": "已完成",
            "self_test_passed": True,
            "max_file_lines": 0,
            "fix_count": 0,
            "blocker_count": 0,
            "overwrite": False,
        },
    }

    # 边界检查: 使用 worktree_guard，包含 untracked 文件，比 git diff --name-only 更不漏。
    try:
        report["boundary_check"] = json.loads(await worktree_guard(
            _run_command_json,
            REPO_ROOT,
            module_key=module_key,
            allowed_prefixes=allowed_prefixes,
            baseline_paths=baseline_paths,
            baseline_status_json=baseline_status_json,
        ))
    except json.JSONDecodeError as exc:
        report["boundary_check"] = {"success": False, "error": str(exc)}
    if module_key and not report["boundary_check"].get("success", False):
        report["success"] = False
        report["risk_note"] = (
            report["risk_note"]
            + f" | [边界违规] outside_allowed={report['boundary_check'].get('outside_allowed', [])[:10]}"
        )

    for item in [p.strip() for p in re.split(r"[,\n]", lint_paths) if p.strip()]:
        try:
            lint_result = json.loads(await code_lint(_run_command_json, REPO_ROOT, _RUFF_CLI, item))
        except json.JSONDecodeError as exc:
            lint_result = {"success": False, "path": item, "error": str(exc)}
        report["lint"].append(lint_result)
        if not lint_result.get("success"):
            report["success"] = False
    if test_targets.strip():
        try:
            test_result = json.loads(await code_run_test(_run_command_json, REPO_ROOT, test_targets))
        except json.JSONDecodeError as exc:
            test_result = {"success": False, "target": test_targets, "error": str(exc)}
        report["tests"].append(test_result)
        if not test_result.get("success"):
            report["success"] = False
    return json.dumps(report, ensure_ascii=False, indent=2)


# ──────────────────── 工作流: plan_task ──────────────────────────────


def _build_evidence_checklist(task_type: str, module_key: str) -> list[dict]:
    checklist = []
    if task_type == "code_change":
        checklist.append({"tool": "code_explore", "reason": "探索相关代码：符号/调用链/影响面", "required": True})
        checklist.append({"tool": "code_node", "reason": "读取关键符号/文件定义", "required": True})
        checklist.append({"tool": "code_impact", "reason": "查看改动影响面", "required": True})
        if module_key:
            checklist.append({"tool": "routes", "params": {"filter": module_key}, "reason": "查模块相关后端端点", "required": True})
            checklist.append({"tool": "capabilities", "params": {"module": module_key}, "reason": "查模块注册能力", "required": True})
            checklist.append({"tool": "db_schema", "reason": "查模块表结构", "required": True})
    elif task_type == "investigation":
        checklist.append({"tool": "code_explore", "reason": "探索问题相关代码", "required": True})
        checklist.append({"tool": "tail_log", "reason": "查看日志排查问题", "required": True})
        checklist.append({"tool": "probe", "reason": "接口验证", "required": False})
    elif task_type == "test":
        checklist.append({"tool": "run_test", "reason": "跑测试看结果", "required": True})
        checklist.append({"tool": "probe", "reason": "接口验证", "required": False})
    return checklist


def _build_boundary(module_key: str) -> dict:
    if not module_key:
        return {
            "type": "framework/global",
            "note": "框架级改动需慎重，影响全部模块。",
        }
    return {
        "type": "module",
        "module": module_key,
        "allowed_dirs": [f"modules/{module_key}/"],
        "forbidden": [
            "禁止直接 import 其他模块代码",
            f"禁止直接读写其他模块的表（只能读写 {module_key}_* 表）",
            "禁止修改 backend/app/、frontend/src/ 或其他模块",
        ],
        "cross_module_rule": "必须通过框架统一通路：runtime SDK 或 /api/modules/call + 能力注册表",
        "validation_guard": f"验收：git diff --name-only 确认所有改动在 modules/{module_key}/ 内",
    }


def _build_verification_plan(task_type: str, module_key: str) -> dict:
    steps = []
    if task_type == "code_change":
        steps.append({"step": "lint", "tool": "lint", "target": "改动过的 Python 文件", "reason": "ruff 静态检查"})
        if module_key:
            test_path = "backend/tests/" if module_key == "framework" else f"modules/{module_key}/sandbox/"
            steps.append({"step": "test", "tool": "run_test", "target": test_path, "reason": "模块测试", "auto": False})
        steps.append({"step": "api_check", "tool": "probe", "target": "/api/health", "reason": "后端健康检查", "auto": True})
        steps.append({"step": "log_check", "tool": "tail_log", "target": "backend", "reason": "确认无新增错误日志", "auto": True})
    return {"steps": steps, "note": "后端改动默认跑测试和 lint；接口类问题优先 probe/call_capability；日志问题先 tail_log"}


def _build_workflow(task_type: str, module_key: str) -> list[dict]:
    steps = []
    if task_type == "code_change":
        steps = [
            {"step": 1, "phase": "全景理解", "action": "调 brief() 了解项目全貌（如未调过）"},
            {"step": 2, "phase": "证据收集", "action": "按 required_evidence checklist 逐一调工具收集证据"},
            {"step": 3, "phase": "方案制定", "action": "基于证据确定具体改哪个文件、怎么改"},
            {"step": 4, "phase": "执行修改", "action": "用 quick_fix_preview 预览 → quick_fix_patch 落盘（或 Read + Edit）"},
            {"step": 5, "phase": "边界检查", "action": f"git diff --name-only 确认改动只在 modules/{module_key}/ 内" if module_key else "git diff 确认改动范围"},
            {"step": 6, "phase": "验证", "action": "按 verification_plan 跑 lint + run_test + probe + tail_log"},
            {"step": 7, "phase": "收尾留痕", "action": "finish_task(汇总+边界检查+风险评估) → memory_write(留痕)"},
        ]
    elif task_type == "investigation":
        steps = [
            {"step": 1, "phase": "问题确认", "action": "调 brief + tail_log 确认问题现象"},
            {"step": 2, "phase": "排查", "action": "code_explore + probe + db_schema 排查根因"},
            {"step": 3, "phase": "结论记录", "action": "memory_write(type='gotcha', ...) 记录排查结论"},
        ]
    elif task_type == "test":
        steps = [
            {"step": 1, "phase": "测试执行", "action": "run_test 跑测试"},
            {"step": 2, "phase": "结果分析", "action": "分析失败原因，确认是否需改代码"},
            {"step": 3, "phase": "结论记录", "action": "memory_write 记录测试结果"},
        ]
    return steps


async def _plan_task(description: str, task_type: str = "code_change", module_key: str = "") -> str:
    """
    标准任务工作流入口.
    任务开始前调此工具，自动做三件事:
    1. 预采部分证据（模块能力 / 表结构）
    2. 生成结构化计划（证据清单 / 边界 / 验证 / 工作流）
    3. 输出分步工作流，agent 须严格按步骤执行
    """
    import time as _time
    started = _time.time()

    plan: dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
            "type": task_type,
            "module": module_key or "(全局/框架)",
            "duration_seconds": 0,
        },
        "problem_understanding": (
            f"任务: {description}\n"
            f"类型: {task_type}\n"
            f"模块: {module_key or '(全局/框架)'}\n"
            "---\n"
            "1. 理解问题后再改代码，禁止猜测\n"
            "2. 证据收集阶段必须调足 required_evidence 中的工具\n"
            "3. 模块改动不可越界\n"
        ),
        "pre_gathered_evidence": {},
        "required_evidence": _build_evidence_checklist(task_type, module_key),
        "modification_boundary": _build_boundary(module_key),
        "verification_plan": _build_verification_plan(task_type, module_key),
        "rollback_and_risk": {
            "rollback_method": "git diff 确认范围；git checkout 回退（如未提交）；memory_write 留痕追溯",
            "risk_level": "medium" if task_type == "code_change" else "low",
            "note": "改动前先 git status 确认工作区干净；模块任务只允许改 modules/{module_key}/ 内" if module_key else "框架级改动需慎重，确认影响全部模块",
        },
        "workflow": _build_workflow(task_type, module_key),
    }

    pre_gather: dict[str, Any] = {}
    if module_key:
        try:
            capabilities_raw, db_schema_raw = await asyncio.gather(
                _capabilities(module_key),
                _db_schema(),
            )
            pre_gather["capabilities"] = json.loads(capabilities_raw) if isinstance(capabilities_raw, str) else capabilities_raw
            pre_gather["db_schema_all"] = json.loads(db_schema_raw) if isinstance(db_schema_raw, str) else db_schema_raw
        except Exception as exc:
            pre_gather["error"] = str(exc)[:200]

        # 从预采的 db_schema 中提取本模块相关表
        if "db_schema_all" in pre_gather and isinstance(pre_gather["db_schema_all"], dict):
            schema_data = pre_gather["db_schema_all"]
            module_tables = {}
            table_prefixes = [module_key, module_key.split("_")[0]] if "_" in module_key else [module_key]
            for prefix in table_prefixes:
                if prefix in schema_data:
                    module_tables[prefix] = schema_data[prefix]
            if module_tables:
                pre_gather["db_schema_module"] = module_tables

    plan["pre_gathered_evidence"] = pre_gather
    plan["metadata"]["duration_seconds"] = round(_time.time() - started, 3)
    return json.dumps(plan, ensure_ascii=False, indent=2)


# ── MCP Server ───────────────────────────────────────────────────────

server = Server(SERVER_NAME)

# ──────────────────── 工具 1: brief ──────────────────────────────────

async def _brief() -> str:
    """项目全景摘要, 取代手读主开发文档."""
    parts = []
    # 主开发文档
    main_doc = REPO_ROOT / "开发文档" / "主开发文档.md"
    if main_doc.exists():
        text = main_doc.read_text(encoding="utf-8")
        lines = text.strip().split("\n")
        # 取前 80 行作为摘要
        summary = "\n".join(lines[:80])
        parts.append(f"## 项目概览\n{summary}\n...")
    else:
        # 改读 README
        readme = REPO_ROOT / "开发文档" / "README.md"
        if readme.exists():
            text = readme.read_text(encoding="utf-8")
            lines = text.strip().split("\n")
            summary = "\n".join(lines[:60])
            parts.append(f"## 项目概览(README)\n{summary}\n...")

    # 变更历史最近 5 条
    changelog = REPO_ROOT / "开发文档" / "变更历史.md"
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        # 取日期标题 + 下面几行
        entries = re.findall(r"(## .*?\n(?:.*?\n)*?)(?=## |\Z)", text)
        recent = entries[:5]
        parts.append("## 最近变更")
        for e in recent:
            parts.append(e.strip())

    # 投递箱信件标题
    inbox_dir = mailbox_outbox_dir(REPO_ROOT)
    if inbox_dir.exists():
        letters = sorted(inbox_dir.glob("*.md"))
        titles = []
        for letter in letters[-10:]:
            first_line = letter.read_text(encoding="utf-8").strip().split("\n")[0].strip("# ").strip()
            titles.append(f"- {letter.stem}: {first_line}")
        parts.append("## 投递箱待处理\n" + "\n".join(titles) if titles else "## 投递箱待处理\n(空)")

    # Git 工作区状态：让 agent 开工就知道是否在 main / 是否 dirty
    try:
        status = await git_status_summary(_run_command_json, REPO_ROOT)
        parts.append("## Git 工作区")
        parts.append(f"- 当前分支: {status.get('branch', '')}")
        parts.append(f"- 未提交条目: {status.get('dirty_count', 0)}")
        if status.get("is_main"):
            parts.append("- 提醒: 当前在 main/master，提交前应先切分支")
        sample = status.get("sample") or []
        if sample:
            parts.append("- 变更样本: " + "；".join(sample[:12]))
    except Exception:
        pass

    # 最近活动: git commit + 项目记忆(带 agent)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--oneline", "-5",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        git_log = stdout.decode().strip()
        if git_log:
            parts.append("## 最近 Git 提交")
            for line in git_log.split("\n"):
                parts.append(f"- {line.strip()}")
    except Exception:
        pass

    memories = list_memories(REPO_ROOT, MEMORY_DIR)[:5]
    if memories:
        parts.append("## 最近项目记忆")
        for m in memories:
            agent = m.get("agent", "unknown")
            parts.append(f"- {m.get('name','')} ({m.get('type','')}) [agent:{agent}] [{', '.join(m.get('tags',[]))}]")

    noise_report = _knowledge_noise_report()
    if noise_report["upload_noise_count"] or noise_report["memory_noise_count"]:
        parts.append("## 知识库污染提示")
        parts.append(
            f"- 可疑上传文件: {noise_report['upload_noise_count']} 个"
            f" | 可疑记忆文件: {noise_report['memory_noise_count']} 个"
        )
        if noise_report["upload_noise_samples"]:
            parts.append("- 上传样本: " + "；".join(noise_report["upload_noise_samples"][:8]))
        if noise_report["memory_noise_samples"]:
            parts.append("- 记忆样本: " + "；".join(noise_report["memory_noise_samples"][:8]))

    try:
        audit = await _workspace_audit()
        table_counts = audit.get("table_counts", [])
        non_zero = [row for row in table_counts if row.get("count", 0)]
        if audit.get("uploads_files", 0) or non_zero:
            parts.append("## 工作区状态")
            parts.append(f"- uploads 文件数: {audit.get('uploads_files', 0)}")
            if non_zero:
                preview = ", ".join(f"{row['table']}={row['count']}" for row in non_zero[:10])
                parts.append("- 非零表: " + preview)
    except Exception:
        pass

    return "\n\n".join(parts)


# ──────────────────── 工具 3: probe ──────────────────────────────────

async def _probe(
    method: str,
    path: str,
    body: str | None = None,
    role: str = "admin",
    max_bytes: int | None = None,
    max_items: int | None = None,
    selector: str | None = None,
    json_path: str | None = None,
) -> str:
    """打后端任意接口, 自动登录."""
    token = await _ensure_live_token(role)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BACKEND_BASE}{path}"
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            try:
                kwargs["json"] = json.loads(body)
            except json.JSONDecodeError:
                kwargs["data"] = body
        resp = await client.request(method, url, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        result = {"status_code": resp.status_code, "data": data}
        options = ResponseShapeOptions(
            selector=selector or json_path,
            max_items=max_items,
            max_bytes=max_bytes,
        )
        return dumps_response(result, options)

# ──────────────────── 工具 3: call_capability ────────────────────────

async def _call_capability(
    module: str,
    action: str,
    params: str = "{}",
    role: str = "admin",
    max_bytes: int | None = None,
    max_items: int | None = None,
    selector: str | None = None,
    json_path: str | None = None,
) -> str:
    """调模块能力(跨模块调用入口)."""
    token = await _ensure_live_token(role)
    body = {
        "target_module": module,
        "action": action,
        "parameters": json.loads(params),
    }

    async def _post_with_token(token_value: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token_value}"}
        async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=60, trust_env=False) as client:
            return await client.post("/api/modules/call", json=body, headers=headers)

    resp = await _post_with_token(token)
    if resp.status_code == 401:
        token = await _ensure_token(role, force_refresh=True)
        _token_cache.pop(role, None)
        resp = await _post_with_token(token)

    try:
        data = resp.json()
    except Exception:
        data = resp.text
    result = {
        "status_code": resp.status_code,
        "data": data,
        "target": {"module": module, "action": action, "role": role},
    }
    options = ResponseShapeOptions(
        selector=selector or json_path,
        max_items=max_items,
        max_bytes=max_bytes,
    )
    return dumps_response(result, options)

# ──────────────────── 工具 4: tail_log ───────────────────────────────

async def _tail_log(module: str = "backend", lines: int = 50) -> str:
    """查看模块日志尾部."""
    lines = min(lines, 500)

    # 直接查模块日志目录
    module_log = LOG_DIR / f"modules/{module}.log"
    if module_log.exists():
        return _tail_file(module_log, lines)

    # 查映射表
    log_file = _LOG_MAP.get(module)
    if log_file:
        path = LOG_DIR / log_file
        return _tail_file(path, lines)

    # 检查 modules/ 子目录
    for p in LOG_DIR.rglob(f"{module}.log"):
        return _tail_file(p, lines)

    # uvicorn 主日志
    main_log = LOG_DIR / "uvicorn.out"
    if main_log.exists():
        return _tail_file(main_log, lines)

    return f"[未找到模块日志] {module}"

# ──────────────────── 工具 5: sql ────────────────────────────────────

async def _sql(query: str) -> str:
    """只读 SQL 查询."""
    try:
        rows = await _execute_sql(query)
        return json.dumps(rows, ensure_ascii=False, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e), "rejected": True}, ensure_ascii=False)

# ──────────────────── 工具 6: web_read ───────────────────────────────

async def _web_read(url: str) -> str:
    """读网页返回 markdown 正文."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ProjectToolkit/1.0)"
            })
            html = resp.text
    except Exception as e:
        return f"[请求失败] {e}"

    # 优先 trafilatura
    try:
        import trafilatura
        text = trafilatura.extract(html, output_format="markdown", include_links=True)
        if text:
            return text
    except ImportError:
        pass

    # 降级: 简单 HTML 正文提取
    text = _html_to_text(html)
    if text:
        return text[:10000]

    return "[无法提取正文]"

def _html_to_text(html: str) -> str:
    """极简 HTML→纯文本."""
    # 去掉 script/style
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # 换行标签变回车
    html = re.sub(r"<\s*(br|/div|/p|/tr|/li|/h[1-6]|/header|/footer|/section)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # 去掉剩余标签
    html = re.sub(r"<[^>]+>", " ", html)
    # 合并空白
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


CORE_TOOL_CONTEXT = CoreToolContext(
    brief=_brief,
    probe=_probe,
    call_capability=_call_capability,
    tail_log=_tail_log,
    clear_log=_clear_log,
    sql=_sql,
    web_read=_web_read,
    start_frontend=_start_frontend,
    sanity_check=_sanity_check,
    smoke_all=_smoke_all,
    release_gate=_release_gate,
    module_sandbox_matrix=_module_sandbox_matrix,
    routes=_routes,
    capabilities=_capabilities,
    db_schema=_db_schema,
    plan_task=_plan_task,
    finish_task=_finish_task,
    knowledge_noise_report=_knowledge_noise_report,
    knowledge_cleanup_noise=_cleanup_knowledge_noise,
    workspace_audit=_workspace_audit,
    workspace_reset=_workspace_reset,
    restart_backend=_restart_backend,
    verify_tool_args=_verify_tool_args,
    snap_diff=_snap_diff,
)

# ── 注册工具 ─────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        *core_tool_definitions(),
        *mailbox_tool_definitions(),
        *memory_tool_definitions(),
        *contract_tool_definitions(),
        *code_tool_definitions(),
        *edit_tool_definitions(),
        *db_reverse_tool_definitions(),
        *insight_tool_definitions(),
        *worktree_tool_definitions(),
        *tool_usage_tool_definitions(),
        *agent_board_tool_definitions(),
        *opencode_tool_definitions(),
        *opencode_pty_tool_definitions(),
    ]

# ── 工具执行 ──────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    started = time.time()
    success = False
    try:
        if core_handles_tool(name):
            result = await core_handle_tool(CORE_TOOL_CONTEXT, name, arguments)
        elif mailbox_handles_tool(name):
            result = await mailbox_handle_tool(REPO_ROOT, name, arguments)
        elif memory_handles_tool(name):
            result = await memory_handle_tool(
                REPO_ROOT,
                MEMORY_DIR,
                EMBEDDING_CACHE_PATH,
                BGE_M3_URL,
                TOOL_USAGE_PATH,
                name,
                arguments,
            )
        elif contract_handles_tool(name):
            result = await contract_handle_tool(REPO_ROOT, name, arguments)
        elif code_handles_tool(name):
            result = await code_handle_tool(_run_command_json, REPO_ROOT, _CODEGRAPH_CLI, _RUFF_CLI, name, arguments)
        elif edit_handles_tool(name):
            result = await edit_handle_tool(_run_command_json, REPO_ROOT, _RUFF_CLI, name, arguments)
        elif db_reverse_handles_tool(name):
            result = await db_reverse_handle_tool(REPO_ROOT, name, arguments)
        elif insight_handles_tool(name):
            result = await insight_handle_tool(REPO_ROOT, TOOL_USAGE_PATH, name, arguments)
        elif worktree_handles_tool(name):
            result = await worktree_handle_tool(_run_command_json, REPO_ROOT, name, arguments)
        elif tool_usage_handles_tool(name):
            result = await tool_usage_handle_tool(REPO_ROOT, TOOL_USAGE_PATH, name, arguments)
        elif agent_board_handles_tool(name):
            result = await agent_board_handle_tool(REPO_ROOT, name, arguments)
        elif opencode_handles_tool(name):
            result = await opencode_handle_tool(REPO_ROOT, name, arguments)
        elif opencode_pty_handles_tool(name):
            result = await opencode_pty_handle_tool(REPO_ROOT, name, arguments)
        else:
            result = json.dumps({"error": f"未知工具: {name}"})
            success = False
            return [TextContent(type="text", text=result)]
        success = True
        return [TextContent(type="text", text=result)]
    except QuickFixError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "rejected": True}, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]
    finally:
        record_tool_usage(TOOL_USAGE_PATH, name, success, time.time() - started, arguments)

# ── 入口 ─────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
