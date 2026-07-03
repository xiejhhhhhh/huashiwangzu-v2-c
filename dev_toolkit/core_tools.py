"""Core tool schemas and routing for the project toolkit MCP server.

The implementation callables still live in server.py because they share a lot of
runtime context. This module keeps MCP discovery and top-level routing
componentized so server.py does not own a long inline tool declaration list.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

TOOL_NAMES = {
    "brief",
    "probe",
    "call_capability",
    "tail_log",
    "clear_log",
    "sql",
    "web_read",
    "start_frontend",
    "sanity_check",
    "smoke_all",
    "release_gate",
    "module_sandbox_matrix",
    "routes",
    "capabilities",
    "db_schema",
    "plan_task",
    "finish_task",
    "knowledge_noise_report",
    "knowledge_cleanup_noise",
    "workspace_audit",
    "workspace_reset",
    "_restart_backend",
    "_verify_tool_args",
    "_snap_diff",
}


@dataclass(frozen=True)
class CoreToolContext:
    brief: Callable[[], Awaitable[str]]
    probe: Callable[
        [str, str, str | None, str, int | None, int | None, str | None, str | None],
        Awaitable[str],
    ]
    call_capability: Callable[
        [str, str, str, str, int | None, int | None, str | None, str | None],
        Awaitable[str],
    ]
    tail_log: Callable[[str, int], Awaitable[str]]
    clear_log: Callable[[str, bool, bool], dict[str, Any]]
    sql: Callable[[str], Awaitable[str]]
    web_read: Callable[[str], Awaitable[str]]
    start_frontend: Callable[[], Awaitable[str]]
    sanity_check: Callable[[], Awaitable[str]]
    smoke_all: Callable[[bool], Awaitable[str]]
    release_gate: Callable[[bool], Awaitable[str]]
    module_sandbox_matrix: Callable[[bool], Awaitable[str]]
    routes: Callable[[str], Awaitable[str]]
    capabilities: Callable[[str], Awaitable[str]]
    db_schema: Callable[[str], Awaitable[str]]
    plan_task: Callable[[str, str, str], Awaitable[str]]
    finish_task: Callable[[str, str, str, str, str, str, str, str, str, str], Awaitable[str]]
    knowledge_noise_report: Callable[[], dict[str, Any]]
    knowledge_cleanup_noise: Callable[[], dict[str, Any]]
    workspace_audit: Callable[[], Awaitable[dict[str, Any]]]
    workspace_reset: Callable[[str, str], Awaitable[dict[str, Any]]]
    restart_backend: Callable[[], Awaitable[dict[str, Any]]]
    verify_tool_args: Callable[[], Awaitable[dict[str, Any]]]
    snap_diff: Callable[[], Awaitable[dict[str, Any]]]


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

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
                    "selector": {
                        "type": "string",
                        "description": "可选 dotted path，仅返回响应中的子树，如 data.data.summary",
                    },
                    "json_path": {
                        "type": "string",
                        "description": "selector 的别名，当前支持 dotted path",
                    },
                    "max_items": {"type": "number", "description": "可选，列表最多保留多少项"},
                    "max_bytes": {"type": "number", "description": "可选，最终 JSON 输出字节上限"},
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
                    "selector": {
                        "type": "string",
                        "description": "可选 dotted path，仅返回响应中的子树，如 data.data.problem_queue",
                    },
                    "json_path": {
                        "type": "string",
                        "description": "selector 的别名，当前支持 dotted path",
                    },
                    "max_items": {"type": "number", "description": "可选，列表最多保留多少项"},
                    "max_bytes": {"type": "number", "description": "可选，最终 JSON 输出字节上限"},
                },
                "required": ["module", "action"],
            },
        ),
        Tool(
            name="tail_log",
            description="查看模块日志尾部。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "模块名, 为空则 backend", "default": "backend"},
                    "lines": {"type": "number", "description": "尾部行数", "default": 50},
                },
            },
        ),
        Tool(
            name="clear_log",
            description="清空项目日志文件, 默认保留 .backend.port 和 .watchdog.pid 等状态文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "模块名, 为空则 backend", "default": "backend"},
                    "all": {"type": "boolean", "description": "是否清空所有 .log 文件", "default": False},
                    "keep_state": {"type": "boolean", "description": "是否保留端口/守护进程状态文件", "default": True},
                },
            },
        ),
        Tool(
            name="sql",
            description="只读 SQL 查询(SELECT/WITH/EXPLAIN).",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "只读 SQL"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="web_read",
            description="读网页返回 markdown 正文. 优先 trafilatura, 降级简单 HTML 提取.",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string", "description": "网页 URL"}},
                "required": ["url"],
            },
        ),
        Tool(
            name="start_frontend",
            description="启动前端开发服务器，等价 cd frontend && npm run dev。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sanity_check",
            description="规范检查: 前端端口、后端健康、模块导入失败、知识图谱卸载风险。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="smoke_all",
            description="一键全回归: 后端集测(probe/call_capability) + 前端UI(Playwright) + 红绿矩阵.",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip_ui": {"type": "boolean", "description": "跳过前端UI测试", "default": False},
                },
            },
        ),
        Tool(
            name="release_gate",
            description="发布前 release gate: 聚合 health/system-status/smoke/队列审计/sandbox 矩阵, 输出 BLOCKER/DEBT/PASS.",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip_ui": {"type": "boolean", "description": "跳过前端UI测试", "default": False},
                },
            },
        ),
        Tool(
            name="module_sandbox_matrix",
            description="模块 sandbox 验收矩阵扫描: 列出全部模块的 sandbox/test_module.py/可自动运行状态.",
            inputSchema={
                "type": "object",
                "properties": {
                    "check": {"type": "boolean", "description": "运行每个 auto-runnable test_module.py", "default": False},
                },
            },
        ),
        Tool(
            name="routes",
            description="从 openapi.json 查准后端端点, 支持按路径过滤.",
            inputSchema={
                "type": "object",
                "properties": {"filter": {"type": "string", "description": "路径关键词过滤", "default": ""}},
            },
        ),
        Tool(
            name="capabilities",
            description="扫描模块 manifest.json 查准模块能力+参数名.",
            inputSchema={
                "type": "object",
                "properties": {"module": {"type": "string", "description": "模块 key, 为空则列出全部", "default": ""}},
            },
        ),
        Tool(
            name="db_schema",
            description="查数据库表结构: 无参数列所有表(按前缀分组), 有 table 参数返回列名+类型.",
            inputSchema={
                "type": "object",
                "properties": {"table": {"type": "string", "description": "表名, 为空则列出所有表", "default": ""}},
            },
        ),
        Tool(
            name="plan_task",
            description=(
                "【标准工作流入口】任务开始前调此工具，自动预采证据并生成结构化计划。"
                "输出含：问题理解、required_evidence 清单、modification_boundary、verification_plan、workflow 步骤。"
                "agent 须严格按 workflow 步骤执行。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "任务描述"},
                    "task_type": {
                        "type": "string",
                        "description": "任务类型: code_change(默认) / investigation / test / docs",
                        "default": "code_change",
                    },
                    "module_key": {"type": "string", "description": "模块 key（如 knowledge、agent），框架/全局任务留空", "default": ""},
                },
                "required": ["description"],
            },
        ),
        Tool(
            name="finish_task",
            description="【收工检查】汇总 Git dirty、边界检查(模块路径越界校验)、可选 lint/test、风险评估、生成 memory_write 留痕模板；不提交、不写记忆。",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "本次任务一句话摘要"},
                    "agent": {"type": "string", "description": "执行 agent 标识", "default": ""},
                    "lint_paths": {"type": "string", "description": "逗号或换行分隔的 Python 文件路径", "default": ""},
                    "test_targets": {"type": "string", "description": "pytest 目标，支持多个空格分隔", "default": ""},
                    "module_key": {"type": "string", "description": "模块 key，用于边界校验", "default": ""},
                    "allowed_prefixes": {
                        "type": "string",
                        "description": "额外允许路径前缀，逗号或换行分隔；传入后覆盖 module_key 默认边界",
                        "default": "",
                    },
                    "baseline_paths": {
                        "type": "string",
                        "description": "开工基线 dirty 路径，支持逗号/换行或 JSON list；这些既有变更不判本轮失败",
                        "default": "",
                    },
                    "baseline_status_json": {
                        "type": "string",
                        "description": "开工时 worktree_guard/git status JSON；会从 changed_files/entries 等字段提取基线路径",
                        "default": "",
                    },
                    "verification_summary": {"type": "string", "description": "验证结果摘要", "default": ""},
                    "risk_note": {"type": "string", "description": "残留风险评估", "default": ""},
                },
                "required": ["summary"],
            },
        ),
        Tool(
            name="knowledge_noise_report",
            description="扫描知识库相关的测试/烟雾/验收污染文件，返回可疑落盘样本与统计。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="knowledge_cleanup_noise",
            description="删除知识库相关的测试/烟雾/验收污染文件(上传目录 + 记忆目录中可疑文件)。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="workspace_audit",
            description="盘点工作区数据现状: 桌面文件/知识库表/上传文件/污染样本。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="workspace_reset",
            description="一键重置工作区数据(需 confirm=RESET, scope=all/desktop/knowledge/files)。",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {"type": "string", "description": "必须传 RESET"},
                    "scope": {"type": "string", "description": "all/desktop/knowledge/files", "default": "all"},
                },
                "required": ["confirm"],
            },
        ),
        Tool(
            name="_restart_backend",
            description="重启后端服务 (kill uvicorn + start_backend.sh). 返回健康检查和端口。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="_verify_tool_args",
            description="存入一条 tool_call 事件并投影为消息, 确认 arguments 是 JSON string 而非 dict.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="_snap_diff",
            description="输出当前未提交 diff 的文件名列表，只检查不用 --name-only 脏检查，结果直接返回。",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


async def handle_tool(context: CoreToolContext, name: str, arguments: dict[str, Any]) -> str:
    if name == "brief":
        return await context.brief()
    if name == "probe":
        return await context.probe(
            arguments["method"],
            arguments["path"],
            arguments.get("body"),
            arguments.get("role", "admin"),
            _optional_int(arguments.get("max_bytes")),
            _optional_int(arguments.get("max_items")),
            arguments.get("selector"),
            arguments.get("json_path"),
        )
    if name == "call_capability":
        return await context.call_capability(
            arguments["module"],
            arguments["action"],
            arguments.get("params", "{}"),
            arguments.get("role", "admin"),
            _optional_int(arguments.get("max_bytes")),
            _optional_int(arguments.get("max_items")),
            arguments.get("selector"),
            arguments.get("json_path"),
        )
    if name == "tail_log":
        return await context.tail_log(arguments.get("module", "backend"), int(arguments.get("lines", 50)))
    if name == "clear_log":
        return json.dumps(
            context.clear_log(
                arguments.get("module", "backend"),
                bool(arguments.get("all", False)),
                bool(arguments.get("keep_state", True)),
            ),
            ensure_ascii=False,
            indent=2,
        )
    if name == "sql":
        return await context.sql(arguments["query"])
    if name == "web_read":
        return await context.web_read(arguments["url"])
    if name == "start_frontend":
        return await context.start_frontend()
    if name == "sanity_check":
        return await context.sanity_check()
    if name == "smoke_all":
        return await context.smoke_all(bool(arguments.get("skip_ui", False)))
    if name == "release_gate":
        return await context.release_gate(bool(arguments.get("skip_ui", False)))
    if name == "module_sandbox_matrix":
        return await context.module_sandbox_matrix(bool(arguments.get("check", False)))
    if name == "routes":
        return await context.routes(arguments.get("filter", ""))
    if name == "capabilities":
        return await context.capabilities(arguments.get("module", ""))
    if name == "db_schema":
        return await context.db_schema(arguments.get("table", ""))
    if name == "plan_task":
        return await context.plan_task(
            arguments["description"],
            arguments.get("task_type", "code_change"),
            arguments.get("module_key", ""),
        )
    if name == "finish_task":
        return await context.finish_task(
            arguments["summary"],
            arguments.get("agent", ""),
            arguments.get("lint_paths", ""),
            arguments.get("test_targets", ""),
            arguments.get("module_key", ""),
            arguments.get("allowed_prefixes", ""),
            arguments.get("baseline_paths", ""),
            arguments.get("baseline_status_json", ""),
            arguments.get("verification_summary", ""),
            arguments.get("risk_note", ""),
        )
    if name == "knowledge_noise_report":
        return json.dumps(context.knowledge_noise_report(), ensure_ascii=False, indent=2)
    if name == "knowledge_cleanup_noise":
        return json.dumps(context.knowledge_cleanup_noise(), ensure_ascii=False, indent=2)
    if name == "workspace_audit":
        return json.dumps(await context.workspace_audit(), ensure_ascii=False, indent=2)
    if name == "workspace_reset":
        return json.dumps(
            await context.workspace_reset(arguments["confirm"], arguments.get("scope", "all")),
            ensure_ascii=False,
            indent=2,
        )
    if name == "_restart_backend":
        return json.dumps(await context.restart_backend(), ensure_ascii=False, indent=2)
    if name == "_verify_tool_args":
        return json.dumps(await context.verify_tool_args(), ensure_ascii=False, indent=2)
    if name == "_snap_diff":
        return json.dumps(await context.snap_diff(), ensure_ascii=False, indent=2)
    raise ValueError(f"未知核心工具: {name}")
