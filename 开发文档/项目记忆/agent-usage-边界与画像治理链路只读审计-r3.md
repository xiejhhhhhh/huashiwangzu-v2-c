---
name: "Agent usage 边界与画像治理链路只读审计 r3"
type: "task"
tags: [audit, agent, usage-tracker, module-boundary, profile-governance, r3]
agent: "codex-agent-profile-usage-boundary-audit-r3"
created: "2026-07-03T10:52:57.069616+00:00"
---

# 做了什么

只读审计两个链路：

1. `backend/app/gateway/usage_tracker.py` 直接 upsert `agent_usage_daily` 是否违反框架/模块边界。
2. `agent_configs` / `agent_role_profiles` / `agent_enterprise_profiles` / `agent_market_profiles` / `agent_checkpoints` 为空，但 `agent_events` / `agent_messages` / `agent_profile_signals` / `agent_user_profile` 非空，判断画像治理链是否断。

本次未修改产品代码，未 commit/push。现场已有其他 agent 的 dirty/untracked 文件，本审计未回滚。

# 核心证据

- `agent_usage_daily` 是 `agent_` 前缀模块表，db_reverse_audit 判定 likely_owner=module:agent，row_count=6；但 `backend/app/gateway/usage_tracker.py:57-78` 直接 SQL 写入该表。
- `log_usage` 调用来自 `backend/app/gateway/router.py` 的网关 chat/image 链路；`capabilities(agent)` 未发现 record_usage/cost 类能力。
- `/api/agent/admin/overview` 当前 cost 统计直接读 `agent_usage_daily`，今日 gateway.chat cost 约 2.8695。
- 表计数：`agent_configs=0`、`agent_role_profiles=0`、`agent_enterprise_profiles=0`、`agent_market_profiles=0`、`agent_checkpoints=0`；`agent_events=1367`、`agent_messages=265`、`agent_profile_signals=194`、`agent_user_profile=4`。
- `agent_user_profile` 不是空链路：owner 4 version=36，profile_data 长度 3930，evolved_at=2026-06-30；owner 1/5 也有演进记录，owner 2 是 `{}`。
- `agent_profile_signals`：152 条 pending auto_evolve 低置信信号（focus 76、habits 67、taboos 9，confidence=0.4），42 条 applied watermark。存在重复证据 count>=2 的 pending 项，如 数据处理、皮肤管理、系统测试、E2E回归测试、给出明确指令、工具调用。
- `RuntimeTaskSink.run_post_turn_hooks()` 会提交 `memory_distill`、`profile_evolve`、`workflow_mine`、`agent_context_compact`；但当前 `/api/health` worker.registered_handlers 只有 `_echo`、kb handlers、`memory_post_save`、`scheduled_agent_job`，缺少 Agent 当前任务 handler。
- `modules/agent/backend/bootstrap.py` 定义 `init_agent_module()` 注册这些 handlers；但 `rg` 仅发现定义和测试，未发现运行时调用。`modules/agent/backend/router.py` 仍 import `.handlers.tasks` 并注释称触发注册，但 `handlers/tasks.py` 当前只定义 handler，注释也说明由 bootstrap 注册。
- `context_pipeline.py` 主链路只读 `AgentConfig` 与个人 `agent_user_profile`；`profile_service.build_profile_injections()` 可组合 user/role/enterprise，但未接入 `_build_system_content()` 主上下文。market profile 也未见主链路注入。
- `RuntimePolicy.enable_checkpointer=False`，所以 `agent_checkpoints=0` 在未显式开启时是预期状态；但 DB 存在 checkpoint 重复索引/约束。

# 结论

1. `usage_tracker.py` 写 `agent_usage_daily` 是边界违规倾向很强：框架网关直接写 Agent 模块业务表。更合适的主修法是把模型网关用量账本迁为框架 owned 表（如 `framework_gateway_usage_daily`），因为成本核算是框架网关公共能力，不应依赖可插拔 Agent 模块。只在产品定义为“Agent 专属成本面板”时，才考虑通过 `agent:record_usage` capability，但这会让核心 gateway 依赖 agent 模块可用性，风险更高。
2. 画像治理不是完全断：个人画像历史上已演进，events/messages/signals/user_profile 形成了部分链路。但当前治理链存在断点：Agent background handlers 当前未注册、四维画像表为空且未接主上下文、pending signal 积压、`profile_evolve.py` 把 dict 赋给 Text 列有潜在写入失败风险。

# 建议修复拆分

- 框架任务：迁移 usage/cost accounting 到 `framework_gateway_usage_daily`，更新 `usage_tracker.py`、网关/系统 cost API、Agent admin overview 的读取来源或兼容视图；回填历史 `agent_usage_daily`；为 log_usage 加单测/集成 probe。
- Agent 模块任务：在模块加载时调用 `init_agent_module()` 或让模块 loader 调标准 bootstrap；修正 router 误导性 import 注释；补 handler 注册 health/smoke 断言。
- Agent 模块任务：`profile.profile_data = json.dumps(merged, ensure_ascii=False)` 或把列迁为 JSON/JSONB，二选一保持模型、服务、DB 一致。
- Agent 模块任务：把 `build_profile_injections()` 或等效组合接入 `context_pipeline._build_system_content()`，明确 role/enterprise/market 的启用策略和种子/管理入口。
- Agent 模块任务：治理 pending signals，增加重复信号合并/老化/可观测指标，避免 0.4 信号长期堆积无反馈。
- Agent 模块任务：明确 checkpoint 默认策略；若继续默认关闭，则 admin/README 标明“空表正常”；清理重复 checkpoint indexes/constraints。

# 验证过

使用 brief、plan_task、worktree_guard、code_explore、routes、capabilities、db_schema、db_reverse_audit、sql、probe、call_capability、tail_log、finish_task、mcp_feedback。未跑 pytest，因为本次是只读审计且无代码改动。
