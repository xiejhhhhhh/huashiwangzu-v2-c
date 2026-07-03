---
name: "post-convergence repair 提交前补漏：job 状态语义、文件锁、stale-orphan、sandbox Python 统一"
type: "task"
tags: [post-convergence, mcp, tool-job, file-lock, stale-orphan, release-gate]
agent: "codex-post-convergence-repair"
created: "2026-07-03T18:38:02.728915+00:00"
---

本轮按提交前补漏信完成 6 个收尾点：tool_job_status 增加 job_success/command_success/clean_success/release_safe，保留 success 兼容 clean pass；PASS_WITH_DEBT 通知改为 completed with debt。tool_job_tools 对 jobs/notifications 的 read-modify-write 增加 fcntl 文件锁，保留原子写。tool_job_status(refresh=true) 对 queued/running 增加 stale/orphaned/stale_reason 判定，并用 stale_notified_at 防重复通知。release_gate.py 抽 _project_python()，sandbox matrix 与 smoke/tool_job 一致优先 backend/.venv/bin/python。新增 test_process_tools.py 覆盖 killpg 成功、ProcessLookupError、OSError fallback、已退出 Popen 不重复 kill。验证：ruff 必跑通过；reset 19 passed；dev_toolkit test_mcp_entry/test_tool_job_tools/test_server_helpers/test_process_tools 57 passed；test_process_tools 单跑 4 passed；node --check 通过；stdio MCP release_gate preflight job 返回 job_success=true command_success=true clean_success=false release_safe=true verdict=PASS_WITH_DEBT，通知为 completed with debt；release_gate --skip-ui --preflight PASS_WITH_DEBT 无 BLOCKER；module_sandbox_matrix --check --json 全 pass；release_gate --skip-ui 复跑 PASS_WITH_DEBT 无 BLOCKER。注意：当前工作区混入另一条模块专项的大量 modules/ 变更，本轮未修改 modules，也未回滚；整体工作区不可直接按本分支提交，需要先隔离/处理模块专项变更。
