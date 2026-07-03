---
name: "profile_evolve 历史任务债只读审计 r3"
type: "task"
tags: [agent, profile_evolve, task_queue, audit, false-success, 20260703]
agent: "profile-evolve-debt-audit-r3"
created: "2026-07-03T10:08:35.713212+00:00"
---

只读审计 task_queue 中 profile_evolve 历史失败与当前链路，未改代码/数据/提交。

关键证据：/api/health 200，worker running，registered_handlers 包含 profile_evolve，task_queue.semantic_failed_completed_24h=0；/api/tasks/worker/audit 显示 profile_evolve completed=190、failed=135，recent_failed_count=0，全部为 historical debt。DB 只读查询：No module named 'init_db' 130 条，时间 2026-06-23T09:51:10Z 至 2026-06-29T06:50:43Z；Failed to parse profile JSON 3 条 failed，时间 2026-06-30T14:05:12Z 至 2026-06-30T17:41:42Z；No messages found 1 条；Orphan startup recovery 1 条。最近 72h profile_evolve 无 failed，最新任务为 completed/skipped no_new_evidence 或 signal_collected。

代码结论：当前 modules/agent/backend/bootstrap.py 通过相对导入 from .services.profile_evolve import handle_profile_evolve 注册 handler；modules/agent/backend/services/profile_evolve.py 当前无裸 init_db import，No messages found 字符串也不在当前 handler 中。backend/app/services/task_worker.py 的 _result_is_semantic_failure 会把 success=false、status failed/error、或 error 且 success 非 true 判为失败；backend/tests/test_task_worker_semantics.py 覆盖该行为。profile_evolve 对 empty/unparseable LLM response 返回 status='failed' + error，backend/tests/test_agent_profile_evolve_soft_failure.py 固定此行为。

发现：P0 无当前可复现 worker/import 断链；P1 backend/app/services/task_debt_governance_service.py 对 Failed to parse profile JSON 的治理理由声称 current handler converts to skipped/soft failure with watermark，但当前源码/测试实际是 status failed 且不写 watermark，非 dry-run retry_once 可能重排旧 JSON 债制造新失败；P2 历史 completed 中还有 6 条 result={error: Failed to parse profile JSON} 的旧假成功（2026-06-24/25），当前 worker 不再新增，但治理服务只扫描 failed，无法收口这类 completed semantic failure；P2 agent handlers/tasks.py 与 bootstrap.py 均注册 profile_evolve，当前 dict 覆盖无害但可清理为单一注册路径。

验证：run_test backend/tests/test_agent_profile_evolve_soft_failure.py 3 passed；run_test backend/tests/test_task_worker_semantics.py 3 passed；run_test backend/tests/test_task_queue_audit.py::test_debt_governance_dedupes_legacy_profile_init_db_failures 1 passed。

修复边界建议：治理分类/审计展示属于 backend/app 框架任务；若要改变 JSON 不可解析为真正 soft-skip/watermark，则属于 modules/agent/profile_evolve 模块任务，并需同步测试与治理文案。
