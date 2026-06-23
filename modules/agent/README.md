# agent — AI assistant

Agent 是桌面壳里的 AI 助手模块，负责对话、工具调用、上下文装配、记忆接入、后台慢任务、子 Agent 和管理台。业务代码只放在 `modules/agent/`，跨模块能力统一走框架 `call_capability`。

## 功能

| 功能 | 说明 |
|---|---|
| 对话 | 多会话、SSE 流式回复、消息/思考/引用/工具事件持久化 |
| 工具发现 | 只暴露 `skill_list` / `skill_describe` / `skill_use` 三个元工具，按需发现模块能力 |
| 引擎 | `engine/` 负责预算分配、上下文压缩、降级链、粘滞检测、记忆和经验注入 |
| 事件溯源 | `agent_events` 记录模型输入、输出、工具调用、压缩、降级等事件，用于回放和诊断 |
| 记忆 | 通过 `memory:*` 能力保存事实、召回记忆、融合摘要、匹配成功经验 |
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

Agent 对外能力通过 manifest 暴露，子 Agent 使用 `agent:spawn_subagent`。

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
| `agent_pending_approvals` | 敏感操作审批 |

## 工具调用结论

`deepseek-v4-flash` 经 opencode-go 返回标准 OpenAI-compatible `choices[0].message.tool_calls`，`arguments` 是 JSON 字符串。工具决策走非流式 `gateway_router.chat`；最终回复走 `gateway_router.chat_stream`。流式 delta 当前不可靠承载工具调用，所以保留正文解析兜底但不作为主路径。

## 边界

- Agent 可 import 框架公开能力：数据库会话、统一响应、权限、模型网关、模块注册、任务队列。
- Agent 不直接 import 其他业务模块代码，不直接读写其他模块业务表。
- 慢工具和后台分析必须经 `SystemTaskQueue`，不能只用进程内 `asyncio.create_task`。
- 管理端接口和敏感操作审批只对 admin 开放。

## 验证

```bash
cd backend && .venv/bin/python -m pytest ../modules/agent/backend/engine/test_compressor.py ../modules/agent/backend/engine/test_stuck_detector.py
cd frontend && npm run build
```
