---
name: "后收敛补漏：MCP 长任务 job 化、reset 级联安全、UI 5.2 假绿修复"
type: "task"
tags: [post-convergence, mcp, tool-job, reset-runtime-data, ui-e2e, release-gate]
agent: "codex-post-convergence-repair"
created: "2026-07-03T18:06:57.364799+00:00"
---

本轮按新投递信完成三条补漏：1) dev_toolkit 新增 process_tools.py 与 tool_job_tools.py，提供 tool_job_submit/status/notifications，将 release_gate、run_test、smoke_all、module_sandbox_matrix、lint 包装为后台 job，状态/日志/通知落 backend/logs，stdio 调用快返；server.py/release_gate.py 的长 subprocess 改为 process group 启动，timeout/cancel 清理整棵进程树。2) reset_runtime_data.py 去掉无条件 CASCADE，新增 FK dependency closure 审计，scope 外 FK 表 apply 时拒绝，TRUNCATE 改 RESTRICT；加强非本地 DB、BACKEND_DATA_DIR、clean-files scope、显式 --scope、backup manifest 校验。3) frontend/tests/ui-e2e.spec.mjs 的 5.2 delete/recycle/restore 与 cleanup fail-closed，passed 包含完整 restore 链路和永久删除清理。验证：ruff 通过；dev_toolkit 60 passed；backend reset 19 passed；node --check 通过；stdio MCP job submit/status/notifications 通过；release_gate --skip-ui --preflight 与 --skip-ui 均 PASS_WITH_DEBT 且无 BLOCKER。未提交。
