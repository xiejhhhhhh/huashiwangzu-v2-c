---
name: "Gateway usage_tracker 框架账本表修复 r3"
type: "task"
tags: [gateway, framework, usage-tracker, module-boundary, r3]
agent: "codex-framework-gateway-usage-boundary-r3"
created: "2026-07-03T11:02:42.241136+00:00"
---

# 我是谁
codex-framework-gateway-usage-boundary-r3。

# 干了什么
修复框架模型网关 usage_tracker 直接写 agent_usage_daily 模块私表的问题：新增框架 ORM 模型 `GatewayUsageDaily`，表名 `framework_gateway_usage_daily`，并把 `backend/app/gateway/usage_tracker.py` 的 UPSERT 改为写框架表；`backend/app/models/__init__.py` 导入新模型，保证 `init_db()` 的 `Base.metadata.create_all` 能初始化该表。

# 改动文件
- `backend/app/models/gateway_usage.py` 新增框架账本模型与唯一约束 `(usage_date, model_key, provider, module)`。
- `backend/app/models/__init__.py` 注册 `GatewayUsageDaily`。
- `backend/app/gateway/usage_tracker.py` 从 `agent_usage_daily` 改写 `framework_gateway_usage_daily`。
- `backend/tests/test_gateway_usage_tracker.py` 新增模型/静态/行为回归测试。

# 验证
- ruff：4 个改动 Python 文件全部通过。
- pytest：`backend/tests/test_gateway_usage_tracker.py backend/tests/test_gateway_retry.py`，17 passed。
- 活系统：`/api/health` 200 且 status ok；`/api/gateway/health` 200。
- 真实 DB 探针：调用 `init_db()` 创建/确认 `framework_gateway_usage_daily`，临时写入 `usage-boundary-probe` 行，读回 `call_count=1/prompt_tokens=100/completion_tokens=50/cost=0.0004`，随后删除该测试行并确认剩余 0 行。
- `rg -n "agent_usage_daily" backend/app` 无命中；backend 日志 tail 无新增输出。

# 边界说明
开工 `worktree_guard` 为 0；收工时工作区出现 dev_toolkit 与 modules/* 的并行脏改，非本任务改动，未触碰也未回退。本任务实际改动只在 `backend/app` 与 `backend/tests`。

# 关联 commit
未 commit/push（用户要求不要 commit/push）。
