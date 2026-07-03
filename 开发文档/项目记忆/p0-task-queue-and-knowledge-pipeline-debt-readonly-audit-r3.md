---
name: "P0 task queue and knowledge pipeline debt readonly audit r3"
type: "task"
tags: [task_queue, knowledge, audit, p0, debt, worker, readonly, r3]
agent: "codex-framework-task-queue-knowledge-debt-audit-r3"
created: "2026-07-03T10:51:39.609144+00:00"
---

只读审计结论（2026-07-03）：

范围：按 brief→plan_task(investigation)→worktree_guard→codegraph/code_explore→routes/capabilities/db_schema/db_reverse_audit→probe/call_capability/tail_log/SQL 从 DB 倒推 task_queue 与 knowledge pipeline 历史债；未改产品代码、未 commit/push。

核心事实：
- /api/health 返回 status=ok，但 task_queue={pending:1,running:0,failed:905,semantic_failed_completed_24h:0}；健康接口只用 semantic_failed_completed_24h 参与 degraded，不因 failed=905 降级。
- /api/tasks/worker/audit：historical_failed_debt_count=905，completed_semantic_failure_count=217，recent_failed_count=0，orphan_running_debt_count=0，future_scheduled_count=1。
- pending=1 是 scheduler scheduled_agent_job id=1050，scheduled_at=2027-01-01 07:59:00+08，不是卡住的 pending。
- failed=905 分布：knowledge/kb_pipeline=769，agent/profile_evolve=135，framework/__emergency08_missing_handler__=1。
- knowledge failed 769 lifecycle join：source_file_row_missing=358，source_file_deleted=286，doc_deleted=81，doc_missing=24，source_file_row_live=20。按更宽测试命名启发，failed 中 test_like_expanded 约 627（file_row_missing 274 + file_deleted 269 + doc_deleted 65 + file_live 19），business_like/非测试命名约 142（file_row_missing 84 + doc_missing 24 + file_deleted 17 + doc_deleted 16 + file_live 1），不能简单全判测试残留。
- error signatures：File not found=710；Parser returned no content blocks=17；Task result status=failed=6；greenlet_spawn=6；Document is already parsing=6；Document N not found 合计 23；DocumentIr object has no attribute get=1。
- agent profile_evolve failed 135：No module named init_db=130（旧 handler/import 债，当前 handler 已不走 init_db），Failed to parse profile JSON=3，No messages found=1（conversation_id=999999 测试债），Orphan task exceeded max retries=1。
- completed semantic failures 217：knowledge/kb_pipeline 210 条 result 仍报 cannot import name get_file_storage_path；agent/profile_evolve 6 条 Failed to parse profile JSON；knowledge/kb_pipeline 1 条 status=failed。它们被旧 worker 记为 completed，是假完成历史债。
- kb_pipeline_runs=112：done=34、degraded=33、skipped=35、failed=6、running=4（复查后当前 running 4 均为诊断表残留，task_id 为空，started_at 在 2026-07-03 00:40-01:34，不对应 SystemTaskQueue running）。stage_runs=400，主要 done/degraded/skipped；failed stage 包括 raw boom=5、profile deadlock=1。kb_pipeline_stale=2581，按 stage：source_file=454、raw=444、fusion=422、profile/graph/relations 各 421；这是 artifact/hash 记录表，不等同未完成任务，但缺少清理/解释口径会污染看板认知。
- knowledge dashboard 当前显示 total_documents=482、failed_documents=430、source_unavailable_documents=430；样本多为 smoke/recycle/access-control/stability-audit/asset_test 等历史测试产物，也有非测试命名的文件 row missing。
- event_bus 另有 file.uploaded failed=2，原因是 2026-06-30 content_package_id column 不存在的旧 schema 债。

代码链路：
- 上传：backend/app/routers/file_transfer.py emit file.uploaded。
- 事件：modules/knowledge/backend/router.py register_module_event_handler("file.uploaded", _on_file_uploaded, "knowledge")，复用 _cap_ingest。
- 登记/入队：modules/knowledge/backend/services/document_service.py register_document → enqueue_pipeline_task，使用 pg_advisory_xact_lock + 查 pending/running 去重，写 framework_system_task_queues kb_pipeline。
- worker：backend/app/services/task_worker.py 每个 uvicorn worker lifespan 启动 task loop；_claim_one_task 用 FOR UPDATE SKIP LOCKED；_result_is_semantic_failure 已能识别 success=false/status failed/error。
- handler：modules/knowledge/backend/services/pipeline_service.py register_task_handler("kb_pipeline", _pipeline_handler)，当前能把 source unavailable/doc missing/doc deleted 转 skipped；失败/降级经 task_worker 语义判断。
- 深流水：pipeline_orchestrator.py 写 kb_pipeline_runs / kb_pipeline_stage_runs；stale_tracker.py 写 kb_pipeline_stale。
- 治理：backend/app/services/task_debt_governance_service.py dry-run 能分类 905 failed + 217 completed semantic failure；knowledge 自己的 pipeline_debt_service 只匹配 File not found / Document % not found / Parser empty，dry-run matched=750，漏掉 19 条 kb_pipeline failed（如 transient/Task result status/greenlet/DocumentIr）。

P0/P1/P2 建议：
- P0：执行一次受控治理任务（dry_run→抽样→非 dry_run 分批），优先用 /api/tasks/worker/governance 的统一分类；不要清表。retry_once 700、mark_obsolete 163、archive_test_debt 2、manual_review 257。先按 task_ids 小批验证：source unavailable retry_once 应转 skipped/obsolete provenance；profile_evolve init_db 去重 retry/obsolete；manual_review 保持不动。
- P0：修正 health/status 门槛或发布门禁：failed=905 和 completed_semantic_failure_total=217 不能只展示不影响状态；至少 status=degraded 或 release_gate 阻断/DEBT 明确分级，避免 ok 掩盖 P0 债。
- P1：补 kb_pipeline_runs 诊断治理：run row 应绑定 task_id，超过阈值 running 且无对应 queue running 的诊断 run 应标 failed/orphan_diagnostic 或 skipped，ingest-status/dashboard 不应把诊断 running 当真运行。
- P1：扩展 knowledge pipeline_debt_service 覆盖 Task result status=failed、greenlet_spawn、Document is already parsing、DocumentIr 旧 bug；或直接废弃重复分类，统一调用 task_debt_governance_service，避免两个口径漂移。
- P1：测试数据治理：smoke/recycle/access-control/stability-audit/asset_test 等自动验收产物应登记清理 owner/file/kb_documents/task_queue/stale/diagnostic 的 cleanup 责任；目前 kb_documents 1419 中大部分是源文件已删除/缺失。
- P1：worker health 多进程状态持久化：uvicorn --workers 3 下每进程都有 task loop，抢占靠 DB 是正确的，但 worker_health.last_active 是进程内变量，health 打到未消费进程会 null；应落 DB/文件 heartbeat 聚合。
- P2：event_bus 历史 failed=2 可归档为 schema migration 历史债；kb_pipeline_stale 应增加页面解释/清理策略（它是 artifact hash 记录，不是全部待执行）。

可拆 worker 任务：
1. framework-task-debt-governance-apply：只做 dry_run 快照、抽样 task_ids 小批非 dry_run、复查 health/audit 水位，不改业务逻辑。
2. knowledge-diagnostic-run-reconcile：为 kb_pipeline_runs 增 task_id 绑定与 orphan running reconcile，补 ingest-status/dashboard 口径测试。
3. knowledge-pipeline-debt-classifier-unify：统一 knowledge pipeline_debt_service 与 task_debt_governance_service，补 19 条漏分类与测试。
4. health-release-gate-debt-signal：调整 /api/health、/api/system/status、release_gate 对 failed_total/completed_semantic_failure_total 的分级。
5. test-data-lifecycle-cleanup：梳理 smoke/sandbox 测试数据清理协议，清理或归档历史 kb/source unavailable 数据。
