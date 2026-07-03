---
name: "OpenCode MCP 后台队列通知与基础安全收口"
type: "task"
tags: [opencode, mcp, dev-toolkit, private-modules, capability-security, background-jobs]
agent: "codex-conductor"
created: "2026-07-03T05:53:19.533173+00:00"
---

本轮收口 OpenCode MCP 后台调用：新增/完善官方 SDK 后台队列、终态通知收件箱、文件锁、PTY 拆分、mcp_self_check 自检；补齐 terminal notification stale snapshot 同步、legacy job 按 job_id 复用通知、终态 refresh 更新 final_text/assistant，并把 job password 改为进程内 secret cache，jobs.json 只保留 has_password。同步修复 private module capability 安全：激活 import 期间自动 owner scope，禁止私有模块覆盖公共/他人 capability，失败时用 registry snapshot 恢复，/api/modules/capabilities 按 caller 过滤私有能力。验证：dev_toolkit 21 passed；backend 132 passed；frontend runtime drift + vue-tsc passed；磁盘 mcp_self_check success=true duplicate/orphan=[]；/api/health ok。commit 待本轮提交。
