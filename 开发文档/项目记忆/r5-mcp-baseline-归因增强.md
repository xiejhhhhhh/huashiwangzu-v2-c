---
name: "R5 MCP baseline 归因增强"
type: "task"
tags: [r5, dev-toolkit, mcp, baseline, worktree-guard]
agent: "codex-r5-mcp-baseline-d"
created: "2026-07-03T11:52:48.148817+00:00"
---

# 改了什么
- 为 `dev_toolkit/worktree_tools.py` 的 `worktree_guard` 增加 `baseline_paths` 与 `baseline_status_json`。
- baseline 支持逗号/换行路径、JSON list、以及 prior `worktree_guard` JSON 的 `changed_files`/`entries` 等字段。
- 输出新增 `baseline_count`、`new_since_baseline`、`new_outside_allowed`、`acknowledged_outside_changes`，并补充 `new_forbidden_hits`，baseline 模式下 success 只因 baseline 后新增越界或新增 forbidden 失败。
- 为 `finish_task` 在 `core_tools.py` 与 `server.py` 透传 baseline 参数，并更新 MCP schema。
- 补测试覆盖旧行为、baseline 已有越界不失败、baseline 后新增越界失败、allowed_prefixes + baseline + 项目记忆组合通过、finish_task 透传和 schema 暴露。

# 验证了什么
- `lint`：`dev_toolkit/worktree_tools.py`、`dev_toolkit/core_tools.py`、`dev_toolkit/server.py`、`dev_toolkit/test_worktree_tools.py`、`dev_toolkit/test_server_helpers.py` 全部 All checks passed。
- `run_test`：`dev_toolkit/test_worktree_tools.py dev_toolkit/test_server_helpers.py`，44 passed。

# 是否还有残留风险
- live MCP server 已在本轮开工前启动，schema 变更需要重启会话/MCP server 后才会完整暴露新参数。
- 工作区存在并行 worker 的 knowledge 与 response shaping 相关 dirty，本任务未修改 knowledge 模块。

# 关联 commit
- 未提交。
