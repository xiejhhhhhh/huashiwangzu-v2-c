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
| `agent_checkpoints` | Agent 执行检查点 |

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
- **执行轨迹** — `track_trajectory=True` 时记录每轮工具调用和结论
- **结构化结果** — 返回每任务的 status/conclusion/rounds_used/error

## 轨迹数据底座

`agent_trajectory_records` 轻量沉淀每轮交互：

- 用户输入、工具调用、工具结果
- 用户纠正、失败与回收
- 思考等级、画像信号
- 用于后续研究、轨迹压缩和工具选择优化（不用于实时决策）

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
