---
name: "knowledge pipeline 问题队列与诊断链路修复节点"
type: "task"
tags: [knowledge, pipeline, debt, status-machine, r3]
agent: "codex-knowledge-pipeline-debt-classifier-r3"
created: "2026-07-03T11:23:48.190652+00:00"
---

节点进展：从 DB/任务队列/状态机反推 knowledge pipeline 断路，确认 framework_system_task_queues 中漏筛错误为 Task result status=failed 6、greenlet_spawn 6、Document is already parsing 6、DocumentIr contract 1；kb_pipeline_runs 有 4 条 task_id 为空的 orphan running。已在 modules/knowledge 内修复 classify_pipeline_debt 候选筛选、error_family 分类、problem_queue 输出、orphan_running_runs/status_machine_audit 诊断，并让新入队 kb_pipeline 参数携带 task_id，pipeline run 诊断行写入 task_id。验证到此节点：ruff 通过；focused tests 27 passed；knowledge sandbox 11 passed；后端重启 health ok。未清理历史数据，治理能力仅 dry-run 诊断。
