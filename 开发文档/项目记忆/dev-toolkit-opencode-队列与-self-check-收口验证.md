---
name: "dev_toolkit OpenCode 队列与 self-check 收口验证"
type: "task"
tags: [dev-toolkit, opencode, mcp, self-check, file-lock, verification]
agent: "codex-devtool-queue-selfcheck-worker"
created: "2026-07-03T05:43:54.126679+00:00"
---

# 改了什么

本轮未做代码补丁；只在 dev_toolkit 范围做收口验证和锁风险审查。

# 验证了什么

- 指定 ruff 命令通过：dev_toolkit/opencode_common.py、opencode_pty_tools.py、opencode_queue.py、opencode_tools.py、insight_tools.py、server.py、test_insight_tools.py、test_mcp_entry.py、test_opencode_tools.py 全部 All checks passed。
- 指定 pytest 通过：dev_toolkit/test_opencode_tools.py、dev_toolkit/test_insight_tools.py、dev_toolkit/test_mcp_entry.py 共 18 passed。
- 本地 Python 直接调用 dev_toolkit.insight_tools.mcp_self_check(Path.cwd(), Path('backend/logs/tool_usage.json'), include_tools=False)，反序列化后 success=true，entrypoint_success=true，duplicate_tools=[]，orphan_tools=[]。
- 额外跑临时并发压力脚本：40 个进程同时通过 _update_job 更新不同 job，最终 missing_updates=[]、notification_count=40、all_completed=True，未复现跨进程丢写。

# 锁审查结论

opencode_queue 当前有 jobs 文件锁与 notifications 文件锁；终态通知路径存在 jobs -> notifications 的嵌套，但未发现 notifications -> jobs 的反向嵌套路径，因此未发现真实死锁环。状态更新采用锁内 read-modify-write + 临时文件 replace；结合压力脚本未发现丢写。

# 是否还有残留风险

工作区有大量其他 worker 的既有脏文件，本轮没有回退也没有触碰 backend/frontend/modules。当前 MCP stdio 进程如果仍是旧代码，用户重启 MCP 后才会加载磁盘新实现。
