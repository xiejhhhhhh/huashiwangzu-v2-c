---
name: "codemap sweep r2 阶段1扫描发现"
type: "task"
tags: [codemap, module-sweep, heartbeat, scan, task_id:codemap-sweep-20260703-r2]
agent: "codex-codemap-sweep-20260703-r2"
created: "2026-07-03T06:56:10.607489+00:00"
---

阶段1完成：已按入口文档、工具台 brief/plan_task/worktree_guard、CodeGraph、routes/capabilities/db_schema 收集证据。当前工作区有其他 worker 的越界脏文件，本任务只碰 modules/codemap/**。问题清单：1) indexer 的 Python/TS/Vue 解析 read/syntax 错误被 parser 内部吞掉，_parse_file 仍 record_file_index，导致 parse_fail_count/confidence 假绿；2) build_full 在扫描 0 文件时仍 finish_build ready=true，stats 可给较高 confidence，存在空索引假成功；3) locks.json 读坏/写清理失败时 check/list/acquire 可静默继续，跨 worker 锁可信度不足；4) check_lock 非法路径返回 locked:false 外层 success true；5) report_inaccuracy HTTP/capability 允许空 path/query_type 写入反馈，后续 empirical_accuracy 和 reliability_note 污染。下一步在 modules/codemap 内修复并补模块测试。
