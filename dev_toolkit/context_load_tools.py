"""context_load — 一次性装弹工具，替代 5-6 次分散调用。

Agent 开工时调一次 context_load(module, task)，返回：
- 模块目录树 + 关键文件
- 对外能力清单（含参数）
- HTTP 接口列表
- 相关数据库表结构
- codegraph 入口符号
- 最近 git 改动（该模块）
- README 摘要

设计目标：一次调用 < 2 秒，返回 < 30KB，够 Agent 直接进入实施。
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

TOOL_NAMES = {"context_load"}
_REPO_ROOT: Path | None = None


def _repo_root() -> Path:
    global _REPO_ROOT
    if _REPO_ROOT is None:
        _REPO_ROOT = Path(__file__).resolve().parents[1]
    return _REPO_ROOT


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="context_load",
            description=(
                "一次性加载模块开工所需全部上下文：目录树、能力清单、接口、表结构、"
                "codegraph入口、最近改动、README。替代 brief+capabilities+routes+"
                "db_schema+code_explore 的 5 次分散调用。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "模块 key（如 knowledge、agent、image-gen）。留空则返回框架层全局上下文。",
                        "default": "",
                    },
                    "task": {
                        "type": "string",
                        "description": "任务简述（用于 codegraph 定位相关符号）。留空只返回结构信息。",
                        "default": "",
                    },
                    "include_schema": {
                        "type": "boolean",
                        "description": "是否包含数据库表结构（大模块可能较长）",
                        "default": True,
                    },
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "context_load":
        return await _context_load(
            repo_root,
            module=arguments.get("module", ""),
            task=arguments.get("task", ""),
            include_schema=arguments.get("include_schema", True),
        )
    return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)


async def _context_load(
    repo_root: Path,
    module: str = "",
    task: str = "",
    include_schema: bool = True,
) -> str:
    """并发收集所有上下文信息，合并返回。"""
    results: dict[str, Any] = {"module": module or "(框架全局)", "task": task or "(未指定)"}

    # 并发执行所有信息收集
    tasks = [
        _gather_directory_tree(repo_root, module),
        _gather_capabilities(repo_root, module),
        _gather_routes(repo_root, module),
        _gather_readme(repo_root, module),
        _gather_git_recent(repo_root, module),
    ]
    if include_schema:
        tasks.append(_gather_db_schema(repo_root, module))
    if task:
        tasks.append(_gather_codegraph(repo_root, module, task))

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    keys = ["directory", "capabilities", "routes", "readme", "git_recent"]
    if include_schema:
        keys.append("db_schema")
    if task:
        keys.append("codegraph")

    for key, value in zip(keys, gathered):
        if isinstance(value, Exception):
            results[key] = {"error": str(value)[:200]}
        else:
            results[key] = value

    return json.dumps(results, ensure_ascii=False, indent=2)


async def _gather_directory_tree(repo_root: Path, module: str) -> dict[str, Any]:
    """模块目录树（2 层深度）+ 关键文件识别。"""
    if module:
        target = repo_root / "modules" / module
    else:
        target = repo_root

    if not target.exists():
        return {"error": f"目录不存在: {target}"}

    tree: list[str] = []
    key_files: list[str] = []
    max_depth = 3 if module else 2

    for item in sorted(target.rglob("*")):
        rel = item.relative_to(target)
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        if any(p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".venv") for p in rel.parts):
            continue

        indent = "  " * (depth - 1)
        name = rel.parts[-1]
        if item.is_dir():
            tree.append(f"{indent}{name}/")
        else:
            tree.append(f"{indent}{name}")
            # 标记关键文件
            if name in ("router.py", "manifest.json", "index.vue", "main.py", "config.py"):
                key_files.append(str(rel))

    return {
        "tree": "\n".join(tree[:80]),  # 限制 80 行
        "key_files": key_files[:20],
    }


async def _gather_capabilities(repo_root: Path, module: str) -> list[dict[str, Any]]:
    """模块对外能力清单（含参数）。"""
    modules_dir = repo_root / "modules"
    results = []

    if module:
        manifest_path = modules_dir / module / "manifest.json"
        if not manifest_path.exists():
            return []
        manifests = [(module, manifest_path)]
    else:
        manifests = [
            (p.parent.name, p)
            for p in sorted(modules_dir.glob("*/manifest.json"))
        ]

    for mod_key, manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        public_actions = manifest.get("public_actions", [])
        if isinstance(public_actions, list):
            for item in public_actions[:15]:  # 限制每模块最多15个
                if isinstance(item, dict):
                    results.append({
                        "module": mod_key,
                        "action": item.get("action", ""),
                        "description": item.get("description", ""),
                        "parameters": item.get("parameters", {}),
                        "min_role": item.get("min_role", "viewer"),
                    })

    # 全局模式只返回摘要
    if not module and len(results) > 30:
        return results[:30]  # 限制总量

    return results


async def _gather_routes(repo_root: Path, module: str) -> list[dict[str, str]]:
    """HTTP 接口清单。"""
    try:
        from dev_toolkit.config_loader import load_config
        config = load_config(repo_root)
        base_url = config.get("backend_base_url", "http://127.0.0.1:33000")

        import httpx
        async with httpx.AsyncClient(base_url=base_url, timeout=5, trust_env=False) as client:
            resp = await client.get("/openapi.json")
            if resp.status_code != 200:
                return [{"error": f"openapi.json 返回 {resp.status_code}"}]
            openapi = resp.json()
    except Exception as e:
        return [{"error": f"无法获取 openapi: {str(e)[:100]}"}]

    paths = openapi.get("paths", {})
    prefix = f"/api/{module}" if module else "/api/"
    routes = []

    for path, methods in paths.items():
        if module and not path.startswith(prefix):
            continue
        for method, detail in methods.items():
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                summary = detail.get("summary", "")
                # 提取参数信息——让Agent知道怎么调
                params = []
                for param in detail.get("parameters", []):
                    params.append(f"{param.get('name')}:{param.get('schema',{}).get('type','')}")
                body_ref = (detail.get("requestBody", {})
                            .get("content", {})
                            .get("application/json", {})
                            .get("schema", {}))
                body_props = body_ref.get("properties", {})
                body_fields = [f"{k}:{v.get('type','')}" for k, v in list(body_props.items())[:8]]

                route_info = {
                    "method": method.upper(),
                    "path": path,
                    "summary": summary,
                }
                if params:
                    route_info["params"] = params
                if body_fields:
                    route_info["body"] = body_fields
                routes.append(route_info)

    return routes[:50]  # 限制


async def _gather_readme(repo_root: Path, module: str) -> str:
    """README 摘要。"""
    if module:
        readme_path = repo_root / "modules" / module / "README.md"
    else:
        readme_path = repo_root / "开发文档" / "README.md"

    if not readme_path.exists():
        return "(无 README)"

    text = readme_path.read_text(encoding="utf-8")
    # 返回全文（已精简到 20-80 行）
    if len(text) > 3000:
        return text[:3000] + "\n...(截断)"
    return text


async def _gather_git_recent(repo_root: Path, module: str) -> list[str]:
    """最近 git 改动（该模块相关）。"""
    try:
        cmd = ["git", "log", "--oneline", "-10"]
        if module:
            cmd.extend(["--", f"modules/{module}/"])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(repo_root),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        lines = stdout.decode().strip().split("\n")
        return [line.strip() for line in lines if line.strip()][:10]
    except Exception as e:
        return [f"git 错误: {str(e)[:100]}"]


async def _gather_db_schema(repo_root: Path, module: str) -> dict[str, Any]:
    """相关数据库表结构。"""
    try:
        from dev_toolkit.config_loader import load_config

        config = load_config(repo_root)
        dsn = config.get("db_dsn", "")
        if not dsn:
            return {"error": "无 db_dsn 配置"}

        # 确定表前缀
        if module:
            # 模块表前缀映射
            prefix_map = {
                "agent": "agent_",
                "knowledge": "kb_",
                "memory": "memory_",
                "im": "im_",
                "scheduler": "scheduler_",
                "douyin-delivery": "douyin_",
                "excel-engine": "excel_",
            }
            prefix = prefix_map.get(module, module.replace("-", "_") + "_")
            query = f"""
                SELECT table_name,
                       string_agg(column_name || ' ' || data_type, ', ' ORDER BY ordinal_position) as columns
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name LIKE '{prefix}%'
                GROUP BY table_name
                ORDER BY table_name
                LIMIT 30
            """
        else:
            # 框架表
            query = """
                SELECT table_name,
                       string_agg(column_name || ' ' || data_type, ', ' ORDER BY ordinal_position) as columns
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name LIKE 'framework_%'
                GROUP BY table_name
                ORDER BY table_name
                LIMIT 20
            """

        proc = await asyncio.create_subprocess_exec(
            "psql", dsn, "-t", "-A", "-F", "|", "-c", query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0:
            return {"error": f"psql 失败: {stderr.decode()[:200]}"}

        tables = {}
        for line in stdout.decode().strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 1)
                tables[parts[0].strip()] = parts[1].strip()

        return {"tables": tables, "count": len(tables)}

    except Exception as e:
        return {"error": f"db_schema 失败: {str(e)[:200]}"}


async def _gather_codegraph(repo_root: Path, module: str, task: str) -> dict[str, Any]:
    """用 codegraph explore 定位相关代码符号。"""
    try:
        query = task
        if module:
            query = f"{module} {task}"

        proc = await asyncio.create_subprocess_exec(
            "codegraph", "explore", query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(repo_root),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0:
            return {"error": f"codegraph 失败: {stderr.decode()[:200]}"}

        output = stdout.decode()
        # 返回完整输出（codegraph explore 默认 maxFiles=12，输出通常 15-30KB）
        # 这是 Agent 定位代码最关键的信息，不截断
        if len(output) > 30000:
            output = output[:30000] + "\n...(超过30KB截断，用 codegraph_node 查具体符号)"

        return {"output": output}

    except Exception as e:
        return {"error": f"codegraph 失败: {str(e)[:200]}"}
