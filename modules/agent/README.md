# agent — AI assistant (V2.0)

Agent 是桌面壳里的 AI 助手模块，负责对话、工具调用、上下文装配、记忆接入、后台慢任务、子 Agent 和管理台。业务代码只放在 `modules/agent/`，跨模块能力统一走框架 `call_capability`。

## 功能 (V2.0)

| 功能 | 说明 |
|---|---|
| 对话 | 多会话、SSE 流式回复、消息/思考/引用/工具事件持久化 |
| 工具发现 | 只暴露 `skill_list` / `skill_describe` / `skill_use` 三个元工具，按需发现模块能力 |
| 引擎 | `engine/` 负责预算分配、上下文压缩、降级链、粘滞检测、记忆和经验注入 |
| 技能治理 | `agent:skill_manage` — 技能 CRUD、审批门禁、使用统计、来源追溯、文件技能兼容 |
| 画像 2.0 | 用户/岗位/企业/市场四维画像体系 + 信号池，低信信号不直接污染正式画像 |
| 子 Agent V2 | 支持单任务/批量任务/工具白名单/写保护/上下文压缩/执行轨迹记录 |
| 事件溯源 | `agent_events` 记录模型输入、输出、工具调用、压缩、降级等事件，用于回放和诊断 |
| 记忆 | 通过 `memory:*` 能力保存事实、召回记忆、融合摘要、匹配成功经验 |
| 轨迹数据 | 轻量 `agent_trajectory_records` 沉淀每轮用户输入/工具调用/结果/纠错/信号 |
| 后台任务 | profile evolve、memory distill、memory dream、slow tool 执行都投递框架任务队列 |
| 治理 | admin 面板查看 overview、审批敏感操作、管理 per-agent 配置 |

## 后端无感 Agent 工作流中枢

Agent workflow 是 `modules/agent/` 内的用户级任务账本，用来记录后台长任务从创建、执行、审批、产物、验证到终态裁判的完整状态。它不复用也不扩展平台级 `framework_workflow_definitions` / `framework_workflow_runs` / `framework_workflow_step_records`，这些表继续作为框架 workflow skeleton 存在；Agent 专属状态只写 `agent_workflow_*` 和相关 `agent_*` 扩展表。

前台默认只显示极简状态：

| 状态 | 含义 |
|---|---|
| `waiting` | 等待开始 |
| `processing` | 正在执行 |
| `needs_confirmation` | 等待用户或管理员确认 |
| `completed` | 所有必需验证通过，干净完成 |
| `failed` | 必需验证失败、审批拒绝或无法恢复 |
| `partial` | 部分完成或带债务完成 |
| `cancelled` | 已取消 |
| `manual_required` | 需要人工接手 |

终态裁判必须依赖验证结果。`PASS_WITH_DEBT` 或 verification `debt` 不能算 `clean_completed`，只能进入 `partial` 或 `completed_with_debt`。任何 `completed` / `failed` / `partial` / `manual_required` 终态都必须至少有一条 `agent_verification_results` 证据。

### Workflow 数据模型

| 表 | 用途 |
|---|---|
| `agent_workflow_runs` | 用户级任务唯一状态来源，记录 owner、title、intent、status、terminal_status、verification_status、queue_task_ids、artifact_summary、dirty_worktree_state、release_gate_verdict 等 |
| `agent_workflow_steps` | 工作流阶段账本，记录 plan/agent/tool/verification/approval/artifact/memory/publish 等步骤及状态流转 |
| `agent_tool_calls` | 工具和 capability 调用账本，保存脱敏参数引用、`arguments_hash`、副作用级别、审批策略、`idempotency_key` 和恢复关联 |
| `agent_workflow_artifacts` | 产物元数据，记录报告、patch、测试结果、截图、文档、日志、临时文件、memory_candidate 等 |
| `agent_verification_results` | 验证结果，覆盖 lint、unit_test、probe、playwright、release_gate、sandbox_matrix、manual_review、boundary_check |
| `agent_failure_records` | 失败、重试和 handoff 记录，支持 tool_error、test_failure、approval_rejected、dirty_worktree、release_gate_fail、timeout 等 |
| `agent_approval_queue` 扩展 | 增加 workflow_run_id、workflow_step_id、tool_call_id、request_type、risk_level、decision_scope、payload_hash、resume_target、expires_at |
| `agent_checkpoints` 扩展 | 增加 workflow_run_id、workflow_step_id、agent_run_id、checkpoint_type、resume_cursor，不破坏既有 conversation checkpoint |

### Workflow 能力与 API

对外能力通过 manifest 声明，真实调用仍走框架统一 capability 通路 `/api/modules/call`：

| 能力 | 用途 |
|---|---|
| `agent:create_workflow` | 创建工作流，初始状态 `waiting` |
| `agent:get_workflow_status` | 返回用户极简状态、verification_status、needs_confirmation、artifact_summary |
| `agent:list_workflows` | 按 owner/admin 权限列出 workflow |
| `agent:list_workflow_steps` | 查看步骤账本 |
| `agent:list_workflow_artifacts` | 查看产物元数据 |
| `agent:record_workflow_step` | 记录或更新步骤状态 |
| `agent:record_tool_call` | 记录工具/capability 调用、参数 hash、副作用级别和 idempotency_key |
| `agent:record_verification` | 记录 pass/fail/debt/skipped/not_applicable 验证结果 |
| `agent:request_workflow_approval` | 创建带 payload_hash 和 resume_target 的可恢复审批 |
| `agent:resolve_workflow_approval` | 按原始审批 payload 恢复处理，批准回到 processing，拒绝进入 failed/partial |
| `agent:finalize_workflow` | 根据 verification 自动裁判 completed/partial/failed/manual_required |

HTTP API 走 `/api/agent` 前缀：

| 端点 | 方法 | 用途 |
|---|---|---|
| `/workflows` | GET/POST | 列表 / 创建 workflow |
| `/workflows/{run_id}` | GET | 查看极简状态；管理员可看 developer_summary |
| `/workflows/{run_id}/steps` | GET/POST | 查看步骤 / 记录步骤 |
| `/workflows/{run_id}/artifacts` | GET/POST | 查看产物元数据 / 记录产物 |
| `/workflows/{run_id}/verifications` | GET/POST | 查看验证结果 / 写入验证结果 |
| `/workflows/{run_id}/tool-calls` | GET/POST | 查看脱敏工具账本 / 记录工具调用 |
| `/workflows/{run_id}/approvals` | POST | 为指定 tool call 创建 workflow 审批 |
| `/workflows/{run_id}/finalize` | POST | 触发终态裁判 |
| `/workflows/{run_id}/failures` | GET | 管理员查看失败记录 |
| `/workflows/{run_id}/cancel` | POST | 取消 workflow |

用户默认不看到完整 tool/MCP/queue 参数；管理员可以展开 steps、tool calls、verifications、failure records、queue_task_ids 和 developer_summary。

### 与队列、审批、checkpoint 的关系

- `framework_system_task_queues` 只作为后台执行队列复用，task parameters 携带 `workflow_run_id`、`workflow_step_id`、`tool_call_id`、`idempotency_key`，不承载用户可见 workflow 真相。
- 敏感动作必须先写 `agent_tool_calls`，再创建 `agent_approval_queue` 记录；审批记录保存 `payload_hash` 和 `resume_target`，批准后恢复原始 tool call，不重新自由生成动作。
- checkpoint 继续服务对话和恢复；新增 workflow 字段只用于把恢复游标归属到某个 run/step/agent_run。
- 项目记忆写入保持降噪，只记录关键结论、终态或人工接手事项，不按每个 workflow step 写记忆。

### Workflow 验收命令

```bash
git diff --name-only
git status --short
backend/.venv/bin/ruff check modules/agent
backend/.venv/bin/python modules/agent/sandbox/test_module.py
backend/.venv/bin/python -m pytest modules/agent/backend/tests -q
backend/.venv/bin/python scripts/check-capability-drift.py
```

如果活栈可用，额外通过 capability 验证 `agent:create_workflow`、`agent:get_workflow_status`、`agent:record_verification`、`agent:finalize_workflow`。

### 本轮不做

- 不做可视化编排器。
- 不做多 agent lane。
- 不做自动 push/publish。
- 不修改或迁移 `framework_workflow_*`。
- 不把 Agent workflow 状态放进纯内存，也不让 `framework_system_task_queues` 成为用户可见真相源。

## 如何调用

HTTP 前缀：`/api/agent`

| 端点 | 方法 | 用途 |
|---|---|---|
| `/chat` | POST | 发起流式对话 |
| `/conversations` | GET/POST | 列出或创建会话 |
| `/conversations/{id}` | PATCH/DELETE | 重命名或删除会话 |
| `/conversations/{id}/messages` | GET | 读取消息、thinking、references、tool_events |
| `/profiles` | GET | 列模型 profile |
| `/tools` | GET | 列当前角色可用工具定义 |
| `/system-prompt` | GET/PUT | 查看/更新系统提示词，PUT 需 admin |
| `/enterprise-prompt` | GET/PUT | 查看/更新企业提示词，PUT 需 admin |
| `/user-profile` | GET | 查看当前用户画像 |
| `/admin/*` | GET/POST/PUT | overview、审批、agent 配置，需 admin |

Agent 对外能力通过 manifest 暴露（20+ 公共能力），子 Agent 使用 `agent:spawn_subagent`（V2 增强版）。

## 引擎文件

| 文件 | 作用 |
|---|---|
| `engine/engine.py` | 组装上下文，连接工具循环和降级链 |
| `engine/event_store.py` | append-only 事件记录和投影 |
| `engine/budget_allocator.py` | token 预算估算和优先级装配 |
| `engine/compressor.py` | 超预算时压缩中间历史 |
| `engine/fallback_chain.py` | 主模型失败后的降级调用 |
| `engine/stuck_detector.py` | 检测重复工具/错误/空响应循环 |
| `engine/layered_memory.py` | 调 memory 模块保存、召回、融合记忆 |
| `engine/experience_memory.py` | 调 memory 模块保存、匹配、反馈成功经验 |

## 数据表

| 表 | 用途 |
|---|---|
| `agent_conversations` | 会话 |
| `agent_messages` | 消息正文 |
| `agent_message_meta` | thinking、references、tool_events |
| `agent_events` | 事件溯源日志 |
| `agent_system_prompt` | 全局系统提示词 |
| `agent_enterprise_prompt` | 企业提示词 |
| `agent_user_profile` | 用户画像 |
| `agent_configs` | per-agent 配置 |
| `agent_approval_queue` | 敏感操作审批 |
| `agent_skill_registry` | 技能注册表（含审批状态） |
| `agent_skill_approvals` | 技能审批请求 |
| `agent_skill_provenance` | 技能变更追溯 |
| `agent_skill_usage` | 技能调用使用统计 |
| `agent_review_tasks` | Review fork 任务 |
| `agent_review_results` | Review fork 提案 |
| `agent_role_profiles` | 岗位/角色画像 |
| `agent_enterprise_profiles` | 企业级画像 |
| `agent_market_profiles` | 市场/产品/品牌/竞品画像 |
| `agent_profile_signals` | 画像信号池 |
| `agent_trajectory_records` | 执行轨迹研究数据 |
| `agent_checkpoints` | Agent 执行检查点（`checkpoint_id` / `step` / `channel_values` / `extra_meta`） |
| `agent_workflow_runs` | Agent 用户级 workflow 任务账本 |
| `agent_workflow_steps` | Agent workflow 步骤账本 |
| `agent_tool_calls` | Agent workflow 工具/capability 调用账本 |
| `agent_workflow_artifacts` | Agent workflow 产物元数据 |
| `agent_verification_results` | Agent workflow 验证结果与终态裁判证据 |
| `agent_failure_records` | Agent workflow 失败与恢复策略记录 |

## 技能治理

`agent:skill_manage` 提供完整的技能生命周期管理：

- **list** — 按 scope/enabled 过滤
- **get** — 查看技能详情（含 body）
- **create** — 新技能（admin 直接 approved；review fork 产物置 pending_approval）
- **update** — 更新技能（from_review 后置回 pending_approval）
- **delete** — 软删除
- **scan** — 扫描 `data/skills/` 下 markdown 文件，自动注册为新技能（保留文件兼容）
- **usage** — 7 天使用聚合（调用量/成功率/平均耗时）
- **provenance** — 技能变更来源追溯
- **pending_approvals** / **approve** / **reject** — 审批门禁

文件与 DB 并存：`scan` 导入的文件技能 approval_status = 'approved'（文件是事实源）；DB 手写技能需审批。

## 画像 2.0

四维画像体系，每维独立：

| 维度 | 表 | 用途 |
|---|---|---|
| 用户画像 | `agent_user_profile` | 个人语气/禁忌/关注/习惯，系统自动进化 |
| 岗位画像 | `agent_role_profiles` | 按岗位设定语气/工具限制/关注领域 |
| 企业画像 | `agent_enterprise_profiles` | 企业文化/业务规则/沟通风格 |
| 市场画像 | `agent_market_profiles` | 产品/品牌/竞品的结构化描述 |

**信号池** (`agent_profile_signals`)：低置信度观察不直接影响正式画像，积累到阈值后由进化流程统一处理。

## 子 Agent V2

`agent:spawn_subagent` V2 增强：

- **单任务/批量** — 支持 `task`（单）和 `tasks`（批量，每项可独立配工具和上下文）
- **工具白名单** — `tools` 参数限制可用工具
- **写保护** — 默认只给读类工具（skill_list/skill_describe + 检索类能力），`write_enabled=True` 才开放写
- **上下文压缩** — 每任务 context 限制在 2000 字符内，系统级长度封顶
- **执行轨迹** — `track_trajectory=True` 时把每个子任务的工具调用、工具结果和结论写入 `agent_trajectory_records`；可传 `conversation_id` / `session_id` 归属到真实对话，否则使用临时负数对话编号；未传 `turn_index_offset` 时自动追加到该对话现有轨迹之后
- **结构化结果** — 返回每任务的 status/conclusion/rounds_used/error

## 轨迹数据底座

`agent_trajectory_records` 轻量沉淀每轮交互：

- 用户输入、工具调用、工具结果
- 用户纠正、失败与回收
- 思考等级、画像信号
- 用于后续研究、轨迹压缩和工具选择优化（不用于实时决策）

## 上下文压缩口径

上下文压缩是预算驱动的运行时能力，不是事后清日志。核心顺序：

1. 先做确定性裁剪：工具输出摘要化、重复 tool_result 去重、长参数裁剪、历史图片/base64 剥离。
2. 再做预算驱动折叠：按 token 预算保留最近 user/assistant/tool 组，切割点必须对齐完整工具调用组。
3. 最后才使用 LLM 结构化摘要：摘要必须写明 Goal、Completed、Blocked、Decisions、Pending，失败时保留原上下文并进入冷却。

压缩产物写入 `agent_context_compactions` / `agent_events` 等持久层，多 worker 下不得依赖进程内集合判断“已折叠”。任何压缩都不能丢掉最新用户目标和未完成工具结果。

## Timeline 与中途草稿

Agent 流式回复在工具调用、inline tool recovery、unfinished tool intent 或最终总结清洗时可能会 rollback/replace 已生成文本。为避免“模型已经对用户说过的中途内容”彻底丢失，运行时把这些文本保存为 timeline 事件：

| 事件类型 | 用途 |
|----------|------|
| `assistant_draft` | 保存被 rollback/replace 的中途回复草稿，刷新后可在“已工作”时间线中折叠查看 |

约定：

- `assistant_draft` 只进 `agent_message_meta.timeline`，不写入 `agent_messages` 正文。
- `assistant_draft` 不进入后续 LLM messages，上下文装配必须自动隔离。
- 前端工作组默认折叠展示草稿，用户需要时展开；刷新后以服务端 timeline 为准。
- 测试必须覆盖草稿保存、空草稿跳过、顺序保持、上下文隔离和 rollback 场景。

## 工具调用结论

`deepseek-v4-flash` 经 opencode-go 返回标准 OpenAI-compatible `choices[0].message.tool_calls`，`arguments` 是 JSON 字符串。`/api/agent/chat` 统一进入 `ConversationRuntime -> ToolLoopRuntime` 主链，工具决策走非流式 `gateway_router.chat`；最终回复走 `gateway_router.chat_stream`。流式 delta 当前不可靠承载工具调用，所以保留正文解析兜底但不作为主路径。

## 边界

- Agent 可 import 框架公开能力：数据库会话、统一响应、权限、模型网关、模块注册、任务队列。
- Agent 不直接 import 其他业务模块代码，不直接读写其他模块业务表。
- 慢工具和后台分析必须经 `SystemTaskQueue`，不能只用进程内 `asyncio.create_task`。
- 管理端接口和敏感操作审批只对 admin 开放。
- 技能治理的信号/统计/谱系数据是辅助决策而非实时拦截。

## 验证

```bash
cd backend && .venv/bin/python -m pytest ../modules/agent/backend/engine/test_compressor.py ../modules/agent/backend/engine/test_stuck_detector.py
cd frontend && npm run build
```
