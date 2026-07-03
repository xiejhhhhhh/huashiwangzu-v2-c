---
name: "OpenCode MCP 后台 job 终态通知收件箱"
type: "task"
tags: [opencode, mcp, dev-toolkit, sdk, queue, notifications, subagent]
agent: "codex"
created: "2026-07-03T05:03:35.477029+00:00"
---

# 改了什么

- 在 `dev_toolkit/opencode_queue.py` 增加 OpenCode SDK job 终态通知收件箱：job 进入 `completed/failed/stalled/timeout/cancelled` 后自动写入 `backend/logs/opencode-sdk-notifications.json`。
- 通知内容包含 job_id、title、status、session_id、letter_path、final_text/error 摘要、assistant_id、message_count 和 next_action；completed 对应 `codex_review`，异常终态对应 `codex_triage`。
- 增加 `list_notifications()`：默认只返回未读通知，可按 status 过滤，可 `mark_read=true` + `acknowledged_by` 标记 Codex 已接手。
- 新增 MCP 工具 `opencode_sdk_job_notifications`，用于 Codex 主线程或外层 watcher 轮询收件箱，形成类似子代理完成通知的接手点。
- 更新 `dev_toolkit/opencode_tools.py` 的 tool schema/handler，更新 `dev_toolkit/README.md` 调用说明，并把新工具加入 `dev_toolkit/test_mcp_entry.py` 必备工具列表。
- 补测试：终态通知只创建一次；已完成历史 job 可回填通知；`mark_read` 后未读收件箱清空；工具注册包含 notifications。

# 验证了什么

- `ruff check dev_toolkit/opencode_queue.py dev_toolkit/opencode_tools.py dev_toolkit/test_opencode_tools.py dev_toolkit/test_mcp_entry.py` 全部通过。
- `pytest dev_toolkit/test_opencode_tools.py dev_toolkit/test_mcp_entry.py`：13 passed。
- 新 Python 进程确认 `opencode_sdk_job_notifications` 已注册，且 completed job 能自动生成 notification。

# 使用口径

- 发任务：`opencode_sdk_job_submit` 或 `opencode_sdk_job_dispatch_letter`。
- 后台轮询：MCP job worker 自动刷新 session messages、停滞时补 continue。
- 主线程接手：重启 MCP 后调用 `opencode_sdk_job_notifications(unread_only=true)` 查未读终态通知；拿到 `job_id` 后再用 `opencode_sdk_job_status(job_id)` 看详情；接手后调用 `opencode_sdk_job_notifications(mark_read=true)` 标已读。

# 残留风险

- 当前运行中的 MCP 进程不会热加载 Python 模块，用户需重启项目工具台 MCP 后新工具才会暴露。
- 工作区已有大量本轮之外 dirty/untracked 文件，本次只处理 OpenCode MCP 工具链。
