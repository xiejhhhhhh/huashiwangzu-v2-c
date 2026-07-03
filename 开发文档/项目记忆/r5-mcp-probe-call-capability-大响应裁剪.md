---
name: "R5 MCP probe/call_capability 大响应裁剪"
type: "task"
tags: [r5, dev-toolkit, mcp, response-trim, probe, call-capability]
agent: "codex-r5-mcp-response-trim-e"
created: "2026-07-03T11:59:42.658063+00:00"
---

# 改了什么

为项目 MCP 的 `probe` / `call_capability` 增加可选响应裁剪：`selector`/`json_path` 支持 dotted path 子树抽取，`max_items` 递归裁剪列表，`max_bytes` 在最终 JSON 超限时保留顶层状态并摘要 data。默认不传参数时保持旧响应结构，不新增 `response_meta`。

核心实现拆到 `dev_toolkit/response_shaping.py`，避免 `server.py` 继续变胖；`dev_toolkit/core_tools.py` 暴露 MCP schema 并转发参数；新增 `dev_toolkit/test_response_tools.py` 覆盖默认兼容、selector、list max_items、max_bytes、无效 selector warning。

# 验证了什么

- `backend/.venv/bin/ruff check dev_toolkit` 通过。
- `pytest dev_toolkit`：133 passed。
- 针对性 `dev_toolkit/test_response_tools.py dev_toolkit/test_server_helpers.py`：42 passed。
- live 验证 `knowledge:classify_pipeline_debt`：`selector=data.data.summary` 返回小 summary；`selector=data.data.problem_queue,max_items=3` 返回 3 条并在 `response_meta.omitted_counts` 标出省略 8 条。

# 残留风险

当前 Codex 会话已连接的 MCP server 仍是旧 schema；需要重启会话/重启项目工具台 MCP 后，新参数才会在工具 schema 中完整暴露。工作区有并行 worker 的 knowledge 模块 dirty，非本任务改动。

# 关联 commit

未提交。
