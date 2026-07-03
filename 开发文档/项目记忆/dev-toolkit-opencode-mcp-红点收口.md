---
name: "dev_toolkit OpenCode MCP 红点收口"
type: "task"
tags: [dev-toolkit, opencode, mcp, concurrency]
agent: "codex-devtool-worker"
created: "2026-07-03T05:35:45.321413+00:00"
---

# 改了什么

- 复核并确认 `dev_toolkit/opencode_tools.py` 当前已包含 `datetime/timezone` 导入，相关 `list_letters` 用例通过。
- 复核 `dev_toolkit/insight_tools.py` 的 `mcp_self_check`：`success` 已包含 `.mcp.json` entrypoint validation、组件 wiring、重复工具与 orphan 工具判断；活工具自检返回 `success=true` 且 `entrypoint.success=true`。
- 在 `dev_toolkit/opencode_queue.py` 增加 per-job monitor `fcntl.flock` 非阻塞锁，避免多个 MCP stdio 进程同时监控同一个 job；同时将 worker loop 内读取 jobs JSON 的路径纳入 `_file_lock(_jobs_path(...))`。

# 验证了什么

- `backend/.venv/bin/ruff check dev_toolkit/opencode_tools.py dev_toolkit/insight_tools.py dev_toolkit/opencode_queue.py dev_toolkit/test_opencode_tools.py dev_toolkit/test_insight_tools.py dev_toolkit/test_mcp_entry.py` -> All checks passed.
- `python3.14 -m pytest dev_toolkit/test_opencode_tools.py dev_toolkit/test_insight_tools.py dev_toolkit/test_mcp_entry.py -q` -> 17 passed.
- 工具台 `run_test` 同目标 -> 17 passed.
- 工具台单文件 `lint` 覆盖 6 个目标文件 -> 全部通过。
- 工具台 `mcp_self_check(include_tools=false)` -> `success=true`, `entrypoint.success=true`。

# 残留风险

- 开工前仓库已有大量 backend/frontend/modules/开发文档 dirty 项；本轮只在 dev_toolkit 范围内 patch forward，没有回滚他人改动。
- `opencode_queue.py`、`opencode_tools.py`、`test_opencode_tools.py` 等 OpenCode 文件当前在 git status 中为 untracked，普通 `git diff --name-only` 不会列出其内容。

# 关联 commit

- 未提交。
