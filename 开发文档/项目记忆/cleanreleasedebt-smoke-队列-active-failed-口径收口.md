---
name: "CleanReleaseDebt smoke 队列 active_failed 口径收口"
type: "task"
tags: [clean-release, release-gate, task-queue, smoke]
agent: "codex-clean-release-debt"
created: "2026-07-05T08:32:29.454189+00:00"
---

本轮继续收口 CleanReleaseDebt：修复 dev_toolkit/smoke.py 的 Z1 队列门禁，使 smoke 改用 /api/tasks/worker/audit 并按 active_failed 计算新增失败，deleted-source obsolete failed 只作为审计信息记录，不再让 smoke 与 release_gate 口径不一致。

验证：ruff 通过；pytest dev_toolkit/test_smoke_queue_gate.py、dev_toolkit/test_release_gate.py、dev_toolkit/test_module_sandbox_matrix.py、backend/tests/test_task_queue_audit.py 为 87 passed / 1 skipped；preflight gate PASS_WITH_DEBT 且无 blocker；两次 full release gate 均确认 queue/lifecycle/pollution/sandbox 非 blocker，第二次 queue failed=0 active_failed=0 pending=0。

剩余：full release gate 仍 BLOCKED，唯一功能 blocker 是受保护的 frontend/tests/ui-e2e.spec.mjs 场景 5.3 Knowledge base - upload file and check analysis 重复超时；本任务禁止修改 UI E2E/相关前端业务。tracked worktree 已提交 d8051f73；仍有其他任务遗留的未跟踪项目记忆文件。
