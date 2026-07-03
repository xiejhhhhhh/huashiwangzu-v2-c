---
name: "OpenCode MCP SDK 后台队列调用补强"
type: "task"
tags: [opencode, mcp, dev-toolkit, sdk, queue, false-green]
agent: "codex"
created: "2026-07-03T04:52:43.033094+00:00"
---

# 改了什么

- 查看前序项目记忆，确认 OpenCode 控制面已收敛到固定 headless `127.0.0.1:55891`，官方 `@opencode-ai/sdk` 是主通路，CLI/PTY 只作兜底。
- 修复 `dev_toolkit/opencode_queue.py` 的异步 job 假完成：`promptAsync` 初始返回的空 assistant 可能带 `cost/tokens`，现在完成只认 assistant `finish` 或 `step-finish`。
- 非终态 job 在 MCP 进程重启后通过 `job_status(refresh=true)` 自动重挂监控线程；已有 `session_id` 的 job 只刷新 messages，不重新投递原始 prompt。
- 刷新 job messages 时同步更新 `last_progress_at`，避免刚看到新消息却按旧时间触发停滞补继续。
- job 列表的 `active_count` 改为统计全队列非终态任务，不再只统计当前分页。
- 补齐 `dev_toolkit/test_mcp_entry.py` 对 `opencode_sdk_job_*` 和 SDK 跟踪工具的入口保障。
- 更新 `dev_toolkit/README.md`，明确短调用走 SDK 同步通路，长任务走 SDK 后台队列。

# 验证了什么

- `ruff check dev_toolkit/opencode_queue.py dev_toolkit/test_opencode_tools.py dev_toolkit/test_mcp_entry.py` 通过。
- `pytest dev_toolkit/test_opencode_tools.py dev_toolkit/test_mcp_entry.py`：11 passed。
- `node --check dev_toolkit/opencode_sdk_client.mjs` 通过。
- 真实 `opencode_sdk_smoke` 走 55891 + 官方 SDK 返回 `MCP_OK`。

# 残留风险

- 当前已运行的 MCP 进程不会热加载 Python 模块，本次 `opencode_queue.py` 修复需要重启项目工具台 MCP 后才会对工具调用生效。
- 工作区已有大量本轮之外的 dirty/untracked 文件，本次未处理。
