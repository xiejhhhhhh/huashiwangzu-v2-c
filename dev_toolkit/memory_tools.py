"""Project memory and MCP feedback tools for the project toolkit MCP server."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from dev_toolkit.tool_usage_tools import read_tool_usage
except ModuleNotFoundError:
    from tool_usage_tools import read_tool_usage


TOOL_NAMES = {"memory_search", "memory_write", "memory_recent", "mcp_feedback", "mcp_feedback_summary"}


def slugify(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = s.strip("-")
    return s or "memory"


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML-like frontmatter from markdown."""
    meta: dict[str, Any] = {"name": "", "type": "reference", "tags": [], "created": "", "body": content}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        body = match.group(2).strip()
        meta["body"] = body
        for line in match.group(1).split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "tags":
                    meta["tags"] = [t.strip().strip('"').strip("'") for t in val.strip("[]").split(",") if t.strip()]
                elif key in ("name", "type", "created", "agent"):
                    meta[key] = val.strip('"').strip("'")
    return meta


def list_memories(repo_root: Path, memory_dir: Path) -> list[dict[str, Any]]:
    """Return all memories sorted by created desc."""
    memories: list[dict[str, Any]] = []
    if not memory_dir.exists():
        return memories
    for path in sorted(memory_dir.iterdir()):
        if path.suffix != ".md" or path.stem.startswith("_"):
            continue
        content = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        meta["slug"] = path.stem
        meta["path"] = str(path.relative_to(repo_root))
        memories.append(meta)
    memories.sort(key=lambda item: item.get("created", ""), reverse=True)
    return memories


def update_index(repo_root: Path, memory_dir: Path) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    index_path = memory_dir / "_索引.md"
    lines = ["# 项目记忆索引\n", "\n", "每条记忆一条记录:\n", "- `[slug](slug.md)` — type — tags — created\n", "\n", "---\n", "\n"]
    for memory in list_memories(repo_root, memory_dir):
        tag_str = ", ".join(memory.get("tags", []))
        lines.append(f"- `[{memory['slug']}]({memory['slug']}.md)` — {memory.get('type','')} — [{tag_str}] — {memory.get('created','')}\n")
    tmp = index_path.with_suffix(".md.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(index_path)


async def get_embedding(bge_m3_url: str, text: str) -> list[float] | None:
    try:
        async with httpx.AsyncClient(base_url=bge_m3_url, timeout=10) as client:
            resp = await client.post("/v1/embeddings", json={"input": text, "model": "bge-m3"})
            if resp.status_code == 200:
                data = resp.json()
                emb = (data.get("data") or [{}])[0].get("embedding")
                if emb:
                    return emb
    except Exception:
        pass
    return None


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def load_embedding_cache(embedding_cache_path: Path) -> dict[str, list[float]]:
    if embedding_cache_path.exists():
        return json.loads(embedding_cache_path.read_text(encoding="utf-8"))
    return {}


def save_embedding_cache(embedding_cache_path: Path, cache: dict[str, list[float]]) -> None:
    embedding_cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = embedding_cache_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(embedding_cache_path)


async def memory_search(repo_root: Path, memory_dir: Path, embedding_cache_path: Path, bge_m3_url: str, query: str, k: int = 5) -> str:
    """Search project memories by semantic embedding, fallback to keyword score."""
    memories = list_memories(repo_root, memory_dir)
    if not memories:
        return json.dumps([], ensure_ascii=False)

    q_emb = await get_embedding(bge_m3_url, query)
    cache = load_embedding_cache(embedding_cache_path)
    scored = []
    for memory in memories:
        text = f"{memory.get('name','')}\n{memory.get('body','')}"
        slug = str(memory["slug"])
        emb = cache.get(slug)
        if q_emb and not emb:
            emb = await get_embedding(bge_m3_url, text[:4000])
            if emb:
                cache[slug] = emb
        if q_emb and emb:
            score = cosine_sim(q_emb, emb)
        else:
            q_terms = set(query.lower().split())
            body = text.lower()
            score = sum(1 for term in q_terms if term in body) / max(len(q_terms), 1)
        scored.append((score, memory))

    if q_emb:
        save_embedding_cache(embedding_cache_path, cache)
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        {
            "score": round(score, 4),
            "slug": memory["slug"],
            "name": memory.get("name", ""),
            "type": memory.get("type", ""),
            "tags": memory.get("tags", []),
            "agent": memory.get("agent", "unknown"),
            "path": memory.get("path", ""),
            "excerpt": memory.get("body", "")[:800],
        }
        for score, memory in scored[:k]
    ]
    return json.dumps(results, ensure_ascii=False, indent=2)


async def memory_write(
    repo_root: Path,
    memory_dir: Path,
    embedding_cache_path: Path,
    bge_m3_url: str,
    type_: str,
    title: str,
    body: str,
    tags: str = "",
    agent: str = "",
) -> str:
    """Write a project memory markdown file and update indexes/cache."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    path = memory_dir / f"{slug}.md"
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    now = datetime.now(timezone.utc).isoformat()
    content = f"""---
name: "{title}"
type: "{type_}"
tags: [{", ".join(tag_list)}]
agent: "{agent}"
created: "{now}"
---

{body.strip()}
"""
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

    update_index(repo_root, memory_dir)

    emb = await get_embedding(bge_m3_url, f"{title}\n{body}"[:4000])
    if emb:
        cache = load_embedding_cache(embedding_cache_path)
        cache[slug] = emb
        save_embedding_cache(embedding_cache_path, cache)

    return json.dumps({"success": True, "slug": slug, "path": str(path.relative_to(repo_root))}, ensure_ascii=False, indent=2)


async def memory_recent(repo_root: Path, memory_dir: Path, n: int = 10) -> str:
    """Return recent project memories."""
    memories = list_memories(repo_root, memory_dir)[:n]
    results = []
    for memory in memories:
        results.append({
            "name": memory.get("name", memory["slug"]),
            "type": memory.get("type", ""),
            "tags": memory.get("tags", []),
            "slug": memory["slug"],
            "created": memory.get("created", ""),
        })
    return json.dumps(results, ensure_ascii=False, indent=2)


def feedback_rating(value: int) -> int:
    return max(1, min(int(value or 3), 5))


async def mcp_feedback(
    repo_root: Path,
    memory_dir: Path,
    tool_usage_path: Path,
    agent: str,
    task_summary: str,
    smoothness: str = "",
    rating: int = 3,
    tools_used: str = "",
    friction: str = "",
    missing_tools: str = "",
    upgrade_suggestions: str = "",
    remove_or_merge_suggestions: str = "",
    notes: str = "",
) -> str:
    """Write a structured markdown feedback record about MCP usability."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    rating = feedback_rating(rating)
    agent = (agent or "unknown").strip()
    task_summary = (task_summary or "未填写任务摘要").strip()
    title = f"工具台反馈-{now.strftime('%Y%m%d-%H%M%S')}-{agent}-{task_summary[:36]}"
    slug = slugify(title)
    path = memory_dir / f"{slug}.md"

    usage = read_tool_usage(tool_usage_path)
    ranked = sorted(
        (
            {
                "tool": name,
                "calls": int(item.get("calls", 0)),
                "error": int(item.get("error", 0)),
                "avg_duration_seconds": round(
                    float(item.get("total_duration_seconds", 0.0)) / max(int(item.get("calls", 0)), 1),
                    3,
                ),
            }
            for name, item in usage.get("tools", {}).items()
        ),
        key=lambda item: (-item["calls"], item["tool"]),
    )[:10]

    body = f"""---
name: "{title}"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "{agent}"
created: "{now.isoformat()}"
---

# MCP 使用反馈

## 任务

{task_summary}

## 顺畅度

- 评分：{rating}/5
- 体感：{smoothness or "未填写"}

## 本次用到的工具

{tools_used or "未填写"}

## 卡点 / 不顺手的地方

{friction or "无"}

## 缺少的工具 / 能力

{missing_tools or "无"}

## 升级建议

{upgrade_suggestions or "无"}

## 建议移除或合并的工具

{remove_or_merge_suggestions or "无"}

## 其他备注

{notes or "无"}

## 当前工具热度快照

```json
{json.dumps(ranked, ensure_ascii=False, indent=2)}
```
"""
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    update_index(repo_root, memory_dir)
    return json.dumps(
        {
            "success": True,
            "path": str(path.relative_to(repo_root)),
            "rating": rating,
            "agent": agent,
            "task_summary": task_summary,
        },
        ensure_ascii=False,
        indent=2,
    )


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\n\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


async def mcp_feedback_summary(repo_root: Path, memory_dir: Path, limit: int = 20) -> str:
    files = sorted(memory_dir.glob("工具台反馈-*.md"), reverse=True)[: max(limit, 1)]
    items: list[dict[str, Any]] = []
    ratings: list[int] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(text)
        body = meta.get("body", text)
        rating_match = re.search(r"评分：(\d+)/5", body)
        rating = int(rating_match.group(1)) if rating_match else None
        if rating is not None:
            ratings.append(rating)
        items.append({
            "path": str(path.relative_to(repo_root)),
            "agent": meta.get("agent", "unknown"),
            "created": meta.get("created", ""),
            "rating": rating,
            "task": extract_markdown_section(body, "任务"),
            "smoothness": extract_markdown_section(body, "顺畅度"),
            "friction": extract_markdown_section(body, "卡点 / 不顺手的地方"),
            "missing_tools": extract_markdown_section(body, "缺少的工具 / 能力"),
            "upgrade_suggestions": extract_markdown_section(body, "升级建议"),
            "remove_or_merge_suggestions": extract_markdown_section(body, "建议移除或合并的工具"),
        })

    upgrade_suggestions = [
        item["upgrade_suggestions"] for item in items
        if item.get("upgrade_suggestions") and item["upgrade_suggestions"] != "无"
    ]
    friction = [
        item["friction"] for item in items
        if item.get("friction") and item["friction"] != "无"
    ]
    payload = {
        "success": True,
        "feedback_count": len(items),
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "latest": items[:5],
        "upgrade_suggestions": upgrade_suggestions[:20],
        "friction": friction[:20],
        "hint": "升级工具台前先看本摘要，再结合 tool_usage_stats 判断高频卡点。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
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
                    "agent": {"type": "string", "description": "执行 agent 标识(如 opencode, claude)", "default": ""},
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
        Tool(
            name="mcp_feedback",
            description="收工时提交本次项目工具台 MCP 使用反馈，写入结构化 Markdown 项目记忆，方便后续升级工具台。",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "反馈 agent 标识，如 codex/opencode/claude"},
                    "task_summary": {"type": "string", "description": "本次任务摘要"},
                    "rating": {"type": "number", "description": "顺畅度评分 1-5", "default": 3},
                    "smoothness": {"type": "string", "description": "本次 MCP 是否顺畅，一句话说明", "default": ""},
                    "tools_used": {"type": "string", "description": "本次关键 MCP 工具，逗号或换行分隔", "default": ""},
                    "friction": {"type": "string", "description": "卡点/不顺手的地方；无则写无", "default": ""},
                    "missing_tools": {"type": "string", "description": "缺少的工具/能力；无则写无", "default": ""},
                    "upgrade_suggestions": {"type": "string", "description": "升级建议；无则写无", "default": ""},
                    "remove_or_merge_suggestions": {"type": "string", "description": "建议移除/合并的工具；无则写无", "default": ""},
                    "notes": {"type": "string", "description": "其他备注", "default": ""},
                },
                "required": ["agent", "task_summary"],
            },
        ),
        Tool(
            name="mcp_feedback_summary",
            description="汇总最近 MCP 使用反馈 Markdown：平均评分、最新反馈、卡点和升级建议。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "读取最近 N 条反馈", "default": 20},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(
    repo_root: Path,
    memory_dir: Path,
    embedding_cache_path: Path,
    bge_m3_url: str,
    tool_usage_path: Path,
    name: str,
    arguments: dict[str, Any],
) -> str:
    if name == "memory_search":
        return await memory_search(
            repo_root,
            memory_dir,
            embedding_cache_path,
            bge_m3_url,
            query=arguments["query"],
            k=int(arguments.get("k", 5)),
        )
    if name == "memory_write":
        return await memory_write(
            repo_root,
            memory_dir,
            embedding_cache_path,
            bge_m3_url,
            type_=arguments["type"],
            title=arguments["title"],
            body=arguments["body"],
            tags=arguments.get("tags", ""),
            agent=arguments.get("agent", ""),
        )
    if name == "memory_recent":
        return await memory_recent(repo_root, memory_dir, n=int(arguments.get("n", 10)))
    if name == "mcp_feedback":
        return await mcp_feedback(
            repo_root,
            memory_dir,
            tool_usage_path,
            agent=arguments["agent"],
            task_summary=arguments["task_summary"],
            smoothness=arguments.get("smoothness", ""),
            rating=int(arguments.get("rating", 3)),
            tools_used=arguments.get("tools_used", ""),
            friction=arguments.get("friction", ""),
            missing_tools=arguments.get("missing_tools", ""),
            upgrade_suggestions=arguments.get("upgrade_suggestions", ""),
            remove_or_merge_suggestions=arguments.get("remove_or_merge_suggestions", ""),
            notes=arguments.get("notes", ""),
        )
    if name == "mcp_feedback_summary":
        return await mcp_feedback_summary(repo_root, memory_dir, limit=int(arguments.get("limit", 20)))
    raise ValueError(f"未知记忆工具: {name}")
