"""
项目工具台 MCP Server
自包含 MCP 服务器, stdio 传输, 暴露 9 个开发工具.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

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

# 确保记忆目录存在
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
EMBEDDING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Token 缓存 ────────────────────────────────────────────────────────

_token_cache: dict[str, dict[str, Any]] = {}  # role -> {"token": str, "expires_at": float}

async def _ensure_token(role: str = "admin") -> str:
    if role not in ACCOUNTS:
        role = "admin"
    now = time.time()
    cached = _token_cache.get(role)
    if cached and cached["expires_at"] > now + 60:
        return cached["token"]
    acct = ACCOUNTS[role]
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=10) as client:
        resp = await client.post("/api/login", json={
            "username": acct["username"],
            "password": acct["password"],
        })
        data = resp.json()
        token = data.get("data", data).get("access_token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"登录失败 {role}: {data}")
        # 缓存1小时(access_token 有效期通常更长)
        _token_cache[role] = {"token": token, "expires_at": now + 3600}
        return token

# ── 嵌入服务 ──────────────────────────────────────────────────────────

async def _get_embedding(text: str) -> list[float] | None:
    # v2 的 bge-m3 是 llama-server(端口30000), OpenAI 兼容 /v1/embeddings
    try:
        async with httpx.AsyncClient(base_url=BGE_M3_URL, timeout=10) as client:
            resp = await client.post("/v1/embeddings", json={"input": text, "model": "bge-m3"})
            if resp.status_code == 200:
                data = resp.json()
                emb = (data.get("data") or [{}])[0].get("embedding")
                if emb:
                    return emb
    except Exception:
        pass
    return None

def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0

def _load_embedding_cache() -> dict[str, list[float]]:
    if EMBEDDING_CACHE_PATH.exists():
        return json.loads(EMBEDDING_CACHE_PATH.read_text(encoding="utf-8"))
    return {}

def _save_embedding_cache(cache: dict[str, list[float]]) -> None:
    tmp = EMBEDDING_CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.rename(EMBEDDING_CACHE_PATH)

# ── 记忆文件操作 ─────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = s.strip("-")
    return s or "memory"

def _list_memories() -> list[dict]:
    """Return all memories sorted by created desc."""
    memories = []
    for f in sorted(MEMORY_DIR.iterdir()):
        if f.suffix != ".md" or f.stem.startswith("_"):
            continue
        content = f.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        fm["slug"] = f.stem
        fm["path"] = str(f.relative_to(REPO_ROOT))
        memories.append(fm)
    memories.sort(key=lambda m: m.get("created", ""), reverse=True)
    return memories

def _parse_frontmatter(content: str) -> dict:
    """Parse YAML-like frontmatter from markdown."""
    meta: dict[str, Any] = {"name": "", "type": "reference", "tags": [], "created": "", "body": content}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if m:
        body = m.group(2).strip()
        meta["body"] = body
        for line in m.group(1).split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "tags":
                    meta["tags"] = [t.strip().strip('"').strip("'") for t in val.strip("[]").split(",") if t.strip()]
                elif key in ("name", "type", "created"):
                    meta[key] = val.strip('"').strip("'")
    return meta

def _update_index() -> None:
    index_path = MEMORY_DIR / "_索引.md"
    lines = ["# 项目记忆索引\n", "\n", "每条记忆一条记录:\n", "- `[slug](slug.md)` — type — tags — created\n", "\n", "---\n", "\n"]
    for m in _list_memories():
        tag_str = ", ".join(m.get("tags", []))
        lines.append(f"- `[{m['slug']}]({m['slug']}.md)` — {m.get('type','')} — [{tag_str}] — {m.get('created','')}\n")
    tmp = index_path.with_suffix(".md.tmp")
    Path(tmp).write_text("".join(lines), encoding="utf-8")
    Path(tmp).rename(index_path)

# ── SQL 只读执行器 ──────────────────────────────────────────────────

# 允许的 SQL 语句前缀
_ALLOWED_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE")
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|EXECUTE|CALL|MERGE)\b",
    re.IGNORECASE,
)

def _check_sql_readonly(query: str) -> None:
    stripped = query.strip().lstrip("(")
    upper = stripped.upper()
    if not upper.startswith(_ALLOWED_PREFIXES):
        # 允许以 WITH 开头的 CTE
        if not upper.startswith("WITH"):
            raise ValueError(f"只允许只读查询 (SELECT/WITH/EXPLAIN), 检测到不允许的语句: {query[:80]}")
    if _FORBIDDEN_KEYWORDS.search(query):
        # 对于 SELECT/WITH 中的子查询, 允许但需要检查外层
        pass

async def _execute_sql(query: str) -> list[dict[str, Any]]:
    _check_sql_readonly(query)
    # 用 psql 执行(也可以用 asyncpg, 但 psql 更通用无需额外包)
    dsn = DB_DSN
    cmd = ["psql", dsn, "-t", "-A", "-F", "\t", "--no-align", "--field-separator=|", "-c", query]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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

# ── MCP Server ───────────────────────────────────────────────────────

server = Server("项目工具台")

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
    inbox_dir = REPO_ROOT.parent / "华世王镞_v2邮箱" / "投递箱"
    if inbox_dir.exists():
        letters = sorted(inbox_dir.glob("*.md"))
        titles = []
        for l in letters[-10:]:
            first_line = l.read_text(encoding="utf-8").strip().split("\n")[0].strip("# ").strip()
            titles.append(f"- {l.stem}: {first_line}")
        parts.append("## 投递箱待处理\n" + "\n".join(titles) if titles else "## 投递箱待处理\n(空)")

    # 最近项目记忆
    memories = _list_memories()[:5]
    if memories:
        parts.append("## 最近项目记忆")
        for m in memories:
            parts.append(f"- {m.get('name','')} ({m.get('type','')}) [{', '.join(m.get('tags',[]))}]")

    return "\n\n".join(parts)

# ──────────────────── 工具 2: probe ──────────────────────────────────

async def _probe(method: str, path: str, body: str | None = None, role: str = "admin") -> str:
    """打后端任意接口, 自动登录."""
    token = await _ensure_token(role)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BACKEND_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
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
        return json.dumps(result, ensure_ascii=False, indent=2)

# ──────────────────── 工具 3: call_capability ────────────────────────

async def _call_capability(module: str, action: str, params: str = "{}", role: str = "admin") -> str:
    """调模块能力(跨模块调用入口)."""
    token = await _ensure_token(role)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "target_module": module,
        "action": action,
        "params": json.loads(params),
    }
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=60) as client:
        resp = await client.post("/api/modules/call", json=body, headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        result = {"status_code": resp.status_code, "data": data}
        return json.dumps(result, ensure_ascii=False, indent=2)

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

# ──────────────────── 工具 7: memory_search ──────────────────────────

async def _memory_search(query: str, k: int = 5) -> str:
    """语义 + 关键词搜索项目记忆."""
    memories = _list_memories()
    if not memories:
        return json.dumps([], ensure_ascii=False)

    # 尝试语义搜索
    query_emb = await _get_embedding(query)
    if query_emb:
        cache = _load_embedding_cache()
        scored = []
        for m in memories:
            slug = m["slug"]
            emb = cache.get(slug)
            if emb is None:
                # 在线算嵌入
                body_text = m.get("body", "")[:512]
                if body_text:
                    emb = await _get_embedding(body_text)
                    if emb:
                        cache[slug] = emb
            if emb:
                score = _cosine_sim(query_emb, emb)
                scored.append((score, m))
        if cache:
            _save_embedding_cache(cache)
        # 按分数排序
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:k]
        results = []
        for score, m in top:
            body_preview = m.get("body", "")[:200]
            results.append({
                "name": m.get("name", m["slug"]),
                "type": m.get("type", ""),
                "tags": m.get("tags", []),
                "slug": m["slug"],
                "body": body_preview,
                "score": round(score, 4),
            })
        return json.dumps(results, ensure_ascii=False, indent=2)

    # 降级: 关键词匹配 (中文无空格, 需二元分词, 否则整串子串匹配必败)
    q = query.lower()
    words = [w.strip() for w in re.split(r'[\s,，、。!?！？:：;；]+', q) if len(w.strip()) > 1]
    # 对含中文的词补充二元分词(字符bigram), 让中文查询能命中
    bigrams = []
    for run in re.findall(r'[一-鿿]{2,}', q):
        bigrams.extend(run[i:i+2] for i in range(len(run) - 1))
    words = list(dict.fromkeys(words + bigrams))  # 去重保序
    if not words:
        words = [q]
    results = []
    for m in memories:
        body = m.get("body", "").lower()
        name = m.get("name", "").lower()
        tag_text = " ".join(m.get("tags", [])).lower()
        # 任一关键词命中即匹配
        matched_words = [w for w in words if w in body or w in name or w in tag_text]
        if matched_words:
            # score = 命中比例
            score = len(matched_words) / len(words)
            if q in name:
                score = max(score, 0.9)
            results.append({
                "name": m.get("name", m["slug"]),
                "type": m.get("type", ""),
                "tags": m.get("tags", []),
                "slug": m["slug"],
                "body": m.get("body", "")[:200],
                "score": round(score, 4),
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:k]
    return json.dumps(results, ensure_ascii=False, indent=2)

# ──────────────────── 工具 8: memory_write ──────────────────────────

async def _memory_write(type_: str, title: str, body: str, tags: str = "") -> str:
    """写入一条项目记忆."""
    valid_types = {"decision", "gotcha", "architecture", "task", "reference"}
    type_ = type_ if type_ in valid_types else "reference"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    slug = _slugify(title)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = MEMORY_DIR / f"{slug}.md"

    # 检查重复
    if filepath.exists():
        return json.dumps({
            "warning": f"记忆已存在 [{slug}], 未覆盖. 如需更新请手动编辑.",
            "slug": slug,
            "path": str(filepath.relative_to(REPO_ROOT)),
        }, ensure_ascii=False, indent=2)

    content = f"""---
name: "{title}"
type: {type_}
tags: [{', '.join(f'"{t}"' for t in tag_list)}]
created: {created}
---

{body}
"""
    filepath.write_text(content.lstrip(), encoding="utf-8")
    _update_index()

    # 算嵌入缓存
    body_text = body[:512]
    emb = await _get_embedding(body_text)
    if emb:
        cache = _load_embedding_cache()
        cache[slug] = emb
        _save_embedding_cache(cache)

    return json.dumps({
        "success": True,
        "slug": slug,
        "path": str(filepath.relative_to(REPO_ROOT)),
    }, ensure_ascii=False, indent=2)

# ──────────────────── 工具 9: memory_recent ─────────────────────────

async def _memory_recent(n: int = 10) -> str:
    """最近 N 条记忆."""
    memories = _list_memories()[:n]
    results = []
    for m in memories:
        results.append({
            "name": m.get("name", m["slug"]),
            "type": m.get("type", ""),
            "tags": m.get("tags", []),
            "slug": m["slug"],
            "created": m.get("created", ""),
        })
    return json.dumps(results, ensure_ascii=False, indent=2)

# ── 注册工具 ─────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="brief",
            description="项目全景摘要: 主开发文档概览 + 最近变更 + 投递箱待处理 + 最近项目记忆",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="probe",
            description="自动登录后打后端任意 HTTP 接口. 返回 {status_code, data}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "HTTP method (GET/POST/PUT/DELETE)"},
                    "path": {"type": "string", "description": "API path, 如 /api/health, /api/agent/conversations"},
                    "body": {"type": "string", "description": "JSON body string (可选)"},
                    "role": {"type": "string", "description": "角色: admin/editor/viewer", "default": "admin"},
                },
                "required": ["method", "path"],
            },
        ),
        Tool(
            name="call_capability",
            description="调模块能力(跨模块调用). 自动登录后打 /api/modules/call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "模块 key, 如 knowledge, agent"},
                    "action": {"type": "string", "description": "能力名, 如 list_templates, search"},
                    "params": {"type": "string", "description": "JSON 参数", "default": "{}"},
                    "role": {"type": "string", "description": "角色: admin/editor/viewer", "default": "admin"},
                },
                "required": ["module", "action"],
            },
        ),
        Tool(
            name="tail_log",
            description="查看模块日志尾部(用于排查错误). module 支持: backend(主日志), agent, auth, knowledge, codemap 等.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "模块名", "default": "backend"},
                    "lines": {"type": "number", "description": "行数", "default": 50},
                },
            },
        ),
        Tool(
            name="sql",
            description="只读 SQL 查询. 强制只允许 SELECT/WITH/EXPLAIN, 写操作被拒绝.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL 查询语句"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="web_read",
            description="读网页返回 markdown 正文. 优先 trafilatura, 降级简单 HTML 提取.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="memory_search",
            description="搜索项目记忆. 优先 bge-m3 语义搜索, 降级关键词匹配.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                    "k": {"type": "number", "description": "返回条数", "default": 5},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="memory_write",
            description="写入项目记忆(决策/踩坑/架构/任务/参考). 自动生成文件 + 更新索引 + 嵌入缓存.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "类型: decision/gotcha/architecture/task/reference"},
                    "title": {"type": "string", "description": "标题"},
                    "body": {"type": "string", "description": "正文"},
                    "tags": {"type": "string", "description": "逗号分隔的标签", "default": ""},
                },
                "required": ["type", "title", "body"],
            },
        ),
        Tool(
            name="memory_recent",
            description="最近 N 条项目记忆.",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {"type": "number", "description": "返回条数", "default": 10},
                },
            },
        ),
    ]

# ── 工具执行 ──────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "brief":
            result = await _brief()
        elif name == "probe":
            result = await _probe(
                method=arguments["method"],
                path=arguments["path"],
                body=arguments.get("body"),
                role=arguments.get("role", "admin"),
            )
        elif name == "call_capability":
            result = await _call_capability(
                module=arguments["module"],
                action=arguments["action"],
                params=arguments.get("params", "{}"),
                role=arguments.get("role", "admin"),
            )
        elif name == "tail_log":
            result = await _tail_log(
                module=arguments.get("module", "backend"),
                lines=arguments.get("lines", 50),
            )
        elif name == "sql":
            result = await _sql(query=arguments["query"])
        elif name == "web_read":
            result = await _web_read(url=arguments["url"])
        elif name == "memory_search":
            result = await _memory_search(
                query=arguments["query"],
                k=int(arguments.get("k", 5)),
            )
        elif name == "memory_write":
            result = await _memory_write(
                type_=arguments["type"],
                title=arguments["title"],
                body=arguments["body"],
                tags=arguments.get("tags", ""),
            )
        elif name == "memory_recent":
            result = await _memory_recent(n=int(arguments.get("n", 10)))
        else:
            result = json.dumps({"error": f"未知工具: {name}"})
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

# ── 入口 ─────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="项目工具台",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
