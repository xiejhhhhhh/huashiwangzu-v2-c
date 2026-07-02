---
name: "reference-upgrade-scout-r4节点2-workflow测试数据污染确认为底座小修"
type: "gotcha"
tags: [reference-upgrade-scout-r4, workflow, test-data-cleanup, db-reverse, gotcha, 20260703]
agent: "reference-upgrade-scout-r4"
created: "2026-07-02T16:53:20.852156+00:00"
---

从 db_reverse_audit 和 /api/workflow/definitions 活系统探测发现 framework_workflow_definitions 全部 540 行都属于 test-workflow/ledger-test/wf-a/wf-b/wf-c/transition-test/step-lifecycle/api-steps/fail-test 这类测试名；每类 60 行，时间覆盖 2026-06-25 到 2026-07-02。CodeGraph 定位到 backend/tests/test_platform_workflow_ledger.py 的 _do_cleanup 只删除 id > 99999，但测试实际写入普通自增 id，因此清理永远不生效。这是很小且确定的测试卫生 bug，适合本轮顺手修复；同时需要清理活库已有测试污染。
