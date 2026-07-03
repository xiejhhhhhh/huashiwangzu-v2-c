---
name: "codemap 模块索引可信度与锁反馈链路质量升级"
type: "task"
tags: [codemap, module-boundary, index-reliability, locks, feedback, rebuild, multi-worker]
agent: "codex-codemap-module-worker-20260703-r1"
created: "2026-07-03T06:33:09.385966+00:00"
---

# 改了什么
- 修复 `modules/codemap/backend/graph/graph.py` 拆分后 `_PROJECT_ROOT` 层级错误，绝对路径 normalize 与 stale 判断恢复到项目根。
- 修复 `_check_file_boundary` 子包相对 import，`module_map` 不再因找不到 `boundary_engine` 500。
- 修复 full rebuild 未清旧图导致 import/call/capability 边重复累积的问题；`begin_build()` 现在清空旧节点和边，新增 rebuild 幂等测试。
- `router.py` 将 graph 内部 `error` 转成统一 `success:false`，覆盖 impact 缺文件、check_boundary 空参数、search 空关键词等假成功；`module-map` HTTP 请求模型去掉误要求的 `path`。
- stats/rebuild 统一补 DB 可信度字段：`query_count`、`feedback_count`、`empirical_accuracy`、`recent_complaints`。
- 文件锁改为持久化到 `modules/codemap/data/locks.json`，校验 agent_id/ttl/仓库外绝对路径，并用模块内 `.gitignore` 忽略运行数据。
- feedback HTTP/capability 写入前确保表存在、路径 normalize，测试反馈已清理。
- README 增加验证矩阵和多 worker 口径：索引是 `process-local`，rebuild 是 `current_worker`，跨 worker 持久化状态是 locks/metrics/feedback。

# 验证了什么
- `ruff check` 覆盖 codemap graph/router/lock/test 文件，全绿。
- `modules/codemap/tests/test_codemap.py` 50 passed；`modules/codemap/sandbox/test_module.py` 18 passed；finish_task 合跑 68 passed。
- 活系统验证：stats、get_file、module_map HTTP+capability、impact 错误守卫、check_boundary 错误守卫、search 错误守卫、rebuild、locks acquire/check/list/release、report/list feedback。
- 测试锁和 feedback 行均已清理；最终 `list_locks` count=0、`list_feedback` items=[]、`feedback_count=0`。
- `git diff --name-only -- modules/codemap` 限定在 codemap 模块；finish_task 边界检查通过。

# 残留风险
- codemap 图索引仍是每个 uvicorn worker 进程内状态，不做跨 worker 共享索引；已显式返回 `index_scope=process-local` / `rebuild_scope=current_worker` 并写入 README。需要全 worker 统一刷新时应重启后端或做独立框架级广播能力。

# 关联 commit
- 未提交。
