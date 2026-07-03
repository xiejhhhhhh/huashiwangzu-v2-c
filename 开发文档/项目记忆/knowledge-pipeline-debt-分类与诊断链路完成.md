---
name: "knowledge pipeline debt 分类与诊断链路完成"
type: "task"
tags: [knowledge, pipeline, debt, verification, r3]
agent: "codex-knowledge-pipeline-debt-classifier-r3"
created: "2026-07-03T11:25:54.107609+00:00"
---

完成：仅在 modules/knowledge/** 与项目记忆范围内修复 knowledge pipeline debt 分类和诊断链路。改动包括：classify_pipeline_debt 扩展 Task result status=failed、greenlet_spawn、Document is already parsing、DocumentIr contract 等错误族；返回 error_summary、problem_queue、orphan_running_runs、status_machine_audit；新入队 kb_pipeline 任务把 task_id 写入 parameters，pipeline_service 传入 orchestrator，kb_pipeline_runs 未来会持久化 task_id。DB 证据：三个指定 marker 各 6 条均已通过 probe 命中；4 条 orphan running 被诊断为 1 source_file_deleted、3 source_file_missing。验证：ruff all passed；knowledge backend tests 45 passed；knowledge backend + sandbox 合跑 56 passed；后端重启 health ok；call_capability classify_pipeline_debt 返回 problem_queue/orphan/status audit。数据清理：未清理/未修改生产数据，全部治理输出为 dry-run 诊断。残留：历史 orphan running 仍未自动 reconcile；历史 source unavailable 文档债务仍作为 problem_queue 暴露。无 commit。
