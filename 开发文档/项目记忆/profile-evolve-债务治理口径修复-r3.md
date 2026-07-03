---
name: "profile_evolve 债务治理口径修复 r3"
type: "task"
tags: [profile_evolve, task_queue, governance, audit, semantic_failure, 20260703]
agent: "profile-evolve-governance-fix-r3"
created: "2026-07-03T10:16:45.939525+00:00"
---

# 改了什么
- `backend/app/services/task_debt_governance_service.py`: `Failed to parse profile JSON` 从 `retry_once` 改为 `manual_review`，原因文案对齐当前 handler 实际返回：`status=failed`、`error=unparseable_llm_profile_json`、`retryable=true`，避免批量重试再次制造失败噪音。
- `backend/app/services/task_debt_governance_service.py`: completed 但 result JSON 含 `success=false`、`status=failed/error` 或非成功 `error` 的任务纳入 `readonly_review` 和 `completed_semantic_failure_manual_review` 分组；非 dry-run 也不修改 completed 行。
- `backend/app/services/task_queue_audit_service.py`: audit 增加 completed semantic failure 只读统计、样本和 manual_review 建议，不改变原 `summary` 与 `historical_debt_total` 口径。
- `backend/tests/test_task_queue_audit.py`: 补 profile parse JSON manual_review、completed semantic failure audit/governance 只读、保留 legacy init_db 去重覆盖。

# 验证了什么
- ruff: `backend/app/services/task_debt_governance_service.py`, `backend/app/services/task_queue_audit_service.py`, `backend/tests/test_task_queue_audit.py` 全通过。
- pytest: `backend/tests/test_task_queue_audit.py` 14 passed。
- pytest: `backend/tests/test_agent_profile_evolve_soft_failure.py` 3 passed，用来确认文案依据的当前 handler 行为。
- probe: `/api/health` 200，`/api/tasks/worker/audit` 200。常驻后端未重启，因此 probe 返回旧进程字段形态。

# 残留风险
- 未重启常驻后端，避免干扰并行代理；新字段需后端下次重启/热更新后出现在活接口。
- 工作区存在 content/knowledge/agent bootstrap 等并行代理脏文件，未触碰；本次目标 diff 仅三个文件。

# 关联 commit
- 未提交。
