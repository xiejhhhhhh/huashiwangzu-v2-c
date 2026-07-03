---
name: "codemap 大域反馈锁能力收口完成"
type: "task"
tags: [codemap, feedback, locks, manifest, sandbox, README, r3]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:13:06.600020+00:00"
---

总收口：codemap 大域任务完成，范围保持 modules/codemap/** + 项目记忆。

问题队列：
1. codemap_feedback=0 时 empirical_accuracy 被表达为 100，形成空样本假满分。已修复为空样本返回 empirical_accuracy=null、empirical_accuracy_status=no_feedback、说明文案。
2. list_feedback 无反馈时只返回 items=[]，反馈闭环不可见。已增加 feedback_count/has_feedback/empty_note/path_count/page/page_size，并让 HTTP 与能力输出一致。
3. report_inaccuracy/list_feedback 覆盖不足。已新增 tests/test_feedback_capabilities.py，覆盖 stats 空态、反馈能力、HTTP list 空态、manifest/action 对齐。
4. codemap:acquire_lock 跨模块能力传 ttl 字符串或 agent_id 非字符串会 500。已在 locks/file_lock.py 做服务层归一；非法 ttl 返回结构化失败。
5. manifest public_actions 参数元数据不完整。已补 acquire_lock.ttl、report_inaccuracy 详情字段、list_feedback 分页字段，并加静态测试防漂移。
6. sandbox/README 未表达反馈空态与锁 ttl 契约。已补。

改动文件：modules/codemap/README.md、manifest.json、backend/feedback_summary.py、backend/router.py、backend/locks/file_lock.py、backend/locks/lock_router.py、tests/test_codemap.py、tests/test_feedback_capabilities.py、sandbox/test_module.py。

验证：ruff 目标文件全过；finish_task 合跑 cd backend && .venv/bin/pytest ../modules/codemap/tests/ ../modules/codemap/sandbox/test_module.py，83 passed；活栈验证 stats/list_feedback/report/cleanup、锁 acquire/check/list/release、非法 ttl 结构化失败、capabilities、check_boundary/module_map/get_file/search 均通过。测试反馈和测试锁均已清理。

残留风险：共享工作区存在其他 agent 的 backend/app、backend/tests、modules/knowledge dirty 文件，finish_task/worktree_guard 因此外部边界失败；本任务未修改这些文件。未 commit/push。
