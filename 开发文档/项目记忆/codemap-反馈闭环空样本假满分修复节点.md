---
name: "codemap 反馈闭环空样本假满分修复节点"
type: "task"
tags: [codemap, feedback, empirical_accuracy, r3]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:05:57.742983+00:00"
---

稳定节点：修复 codemap_feedback=0 时 stats 把 empirical_accuracy 表达成 100 的假满分问题。

改动范围：仅 modules/codemap/**。

已完成：
- 新增 modules/codemap/backend/feedback_summary.py，统一生成 empirical_accuracy 与 list_feedback 空态 metadata。
- modules/codemap/backend/router.py：_enrich_stats_with_db 在 feedback_count=0 时返回 empirical_accuracy=None、empirical_accuracy_status=no_feedback、说明文案；list_feedback 能力返回 has_feedback/feedback_count/empty_note，并补出 codemap_said/actual。
- modules/codemap/backend/locks/lock_router.py：HTTP /api/codemap/list-feedback 与能力输出口径对齐。
- modules/codemap/tests/test_feedback_capabilities.py：覆盖无反馈、测量反馈、report_inaccuracy/list_feedback 能力、HTTP list-feedback 空态。
- modules/codemap/sandbox/test_module.py 与 README.md 增加无反馈不能视为 100% 的契约提示。

验证：ruff 目标文件通过；../modules/codemap/tests/ 62 passed；../modules/codemap/sandbox/test_module.py 19 passed；重启后端后活栈验证 stats/list_feedback/report_inaccuracy/list_feedback/cleanup 全通过，清理后 codemap_feedback=0 且 empirical_accuracy=null/no_feedback。

注意：工作区存在其他 agent 的非 codemap dirty 文件，未触碰。未 commit/push。
