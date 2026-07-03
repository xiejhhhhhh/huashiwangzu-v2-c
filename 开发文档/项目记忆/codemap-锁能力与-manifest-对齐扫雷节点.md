---
name: "codemap 锁能力与 manifest 对齐扫雷节点"
type: "task"
tags: [codemap, locks, manifest, sandbox, r3]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:11:46.821004+00:00"
---

稳定节点：继续 codemap 大域扫雷，修复锁能力入口参数 500，并对齐 manifest/sandbox/README。

问题队列与处理：
1. 跨模块能力 codemap:acquire_lock 对 ttl 字符串或 agent_id 非字符串缺少服务层归一，活栈复现为 500。修复 modules/codemap/backend/locks/file_lock.py：path/agent_id/ttl 在锁服务层归一；ttl="60" 接受为 60；ttl="abc" 返回结构化失败，不再 500。
2. manifest public_actions 与 register_capability action 名称对齐，但元数据缺 ttl、report_inaccuracy 详情字段、list_feedback 分页字段。已更新 modules/codemap/manifest.json，并新增静态测试防漂移。
3. sandbox 未表达 acquire_lock ttl 与反馈空态契约。已更新 modules/codemap/sandbox/test_module.py。
4. README 未完整说明 feedback/list 空态和能力 metadata 口径。已更新 modules/codemap/README.md。

验证：
- ruff 目标文件全部通过。
- cd backend && .venv/bin/python -m pytest ../modules/codemap/tests/：64 passed。
- cd backend && .venv/bin/python -m pytest ../modules/codemap/sandbox/test_module.py：19 passed。
- capabilities(module=codemap) 显示 acquire_lock.ttl、report_inaccuracy codemap_said/actual/reason/agent_id、list_feedback page/page_size。
- 重启后端后活栈验证：ttl 字符串和数字 agent_id 不再 500；非法 ttl 返回结构化失败；list_locks/release 后为空；stats/list_feedback 空反馈仍为 empirical_accuracy=null/no_feedback；check_boundary(module_key=codemap) compliant true；module_map 暴露 13 个 codemap 能力；新增 feedback_summary 可被 get_file/search 索引。

注意：工作区存在其他 agent 的 backend/knowledge dirty 文件，worktree_guard 因此整体失败；本节点未触碰这些文件。未 commit/push。
