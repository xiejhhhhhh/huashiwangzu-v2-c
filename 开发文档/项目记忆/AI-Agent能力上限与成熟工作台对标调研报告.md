# AI Agent 能力上限与成熟工作台对标调研报告

## 1. 结论摘要

当前 Agent 已经超过“聊天助手”和普通“工具调用器”。它具备较完整的 Agent 底座：SSE 对话、渐进式工具发现、跨模块 capability 调用、事件溯源、上下文预算与压缩、记忆与经验注入、敏感操作审批、子 Agent、后台任务、workflow run/step/tool/artifact/verification/failure 账本。

但它还没有稳定进入“真正工作中枢”阶段。核心原因不是缺表或缺 API，而是主链路还没有做到：每个用户任务自动创建 workflow，自动拆 plan/step，所有工具调用自动落账，失败自动诊断与重试，产物自动进入发布/验证闭环，用户只看极简状态，管理员能追完整执行链。

当前综合成熟度：**6.4/10**。

定位判断：**强 Agent 底座 + 初步工作流账本，正在从聊天工具向工作中枢过渡**。如果只看模块能力和表结构，接近 7 分；如果看真实活系统的默认消费程度，仍在 6 分区间。只读探针显示 `/api/agent/workflows?limit=5` 和 `agent:list_workflows` 可用，但当前 `items=[]`，说明账本能力已通，尚未成为默认任务主链。

最短板的 5 个能力：

1. **任务自动规划与 workflow 主链绑定**：workflow ledger 已有，但 chat/tool loop 尚未默认把每轮任务写成 run/step/tool/verification。
2. **失败恢复与自我纠错策略**：已有 stuck detector、fallback、failure records，但更多是停止/记录，缺少重规划、换工具、缩小任务、handoff。
3. **验证驱动的终态裁判**：`finalize_workflow` 强制 verification，这点正确；但 lint/test/probe/release gate 还没有成为 Agent 自动执行内循环。
4. **多 Agent 协作治理**：已有 `spawn_subagent`，但缺少 lane、claim/release、依赖、结果 schema、汇总裁判、冲突处理。
5. **产物发布与桌面闭环**：已有 artifact ledger，但缺产物卡片、预览、版本、发布、撤销、下载、回滚的默认用户路径。

最值得下一轮升级的 5 个能力：

1. **Workflow 执行语义收口**：把 run/step/tool/verification/failure 接入 tool loop 主链。
2. **工具调用可靠性与 Problem Matcher**：把 lint/test/probe/terminal 输出解析为结构化问题和验证证据。
3. **Agentic Knowledge 与项目记忆统一**：语义搜索之外补 tree/grep/read_lines/citation_bundle，打通产品记忆和项目记忆口径。
4. **审批与恢复硬化**：所有危险动作按 `tool_call_id + payload_hash + resume_target` 恢复原动作，不重新自由生成。
5. **多 Agent 工作队列**：从裸子 Agent 升级为 work item、角色、工具白名单、lease、stale 回收、review gate。

## 2. 调研范围与证据

读取的项目文档：

- `AGENTS.md`
- `开发文档/README.md`
- `开发文档/01_框架开发文档/README.md`
- `开发文档/02_底层开发文档/README.md`
- `开发文档/03_模块开发文档/README.md`
- `modules/agent/README.md`
- `modules/memory/README.md`
- `modules/knowledge/README.md`
- `dev_toolkit/README.md`
- `开发文档/项目记忆/执行信-后端无感Agent工作流中枢完整落地.md`
- `开发文档/项目记忆/执行信-数据库反向链路主链路闭环修复.md`
- `开发文档/项目记忆/调研信-产品化闭环桌面体验与测试发布效率总审计.md`
- `开发文档/项目记忆/后端无感Agent工作流中枢调研报告.md`
- `开发文档/项目记忆/后端无感-agent-工作流中枢落地.md`

读取和探索的代码区域：

- `modules/agent/backend/runtime/tool_loop_runtime.py`
- `modules/agent/backend/runtime/conversation_runtime.py`
- `modules/agent/backend/runtime/runtime_policy.py`
- `modules/agent/backend/engine/context_pipeline.py`
- `modules/agent/backend/engine/layered_memory.py`
- `modules/agent/backend/engine/experience_memory.py`
- `modules/agent/backend/engine/tool_orchestrator.py`
- `modules/agent/backend/services/workflow_service.py`
- `modules/agent/backend/services/action_policy.py`
- `modules/agent/backend/services/tool_discovery.py`
- `modules/agent/backend/services/review_service.py`
- `modules/agent/backend/workflow_models.py`
- `modules/agent/backend/router.py`
- `modules/agent/backend/handlers/workflow.py`
- `modules/agent/frontend/components/WorkflowList.vue`
- `modules/agent/frontend/components/WorkflowDetail.vue`
- `modules/agent/frontend/components/WorkflowStatusBadge.vue`
- `modules/agent/frontend/components/WorkTraceGroup.vue`
- `modules/agent/frontend/components/ToolCallCard.vue`
- `modules/agent/frontend/admin/ApprovalPanel.vue`
- `modules/memory/`
- `modules/knowledge/`
- `modules/terminal-tools/`
- `modules/desktop-tools/`
- `modules/codemap/`
- `dev_toolkit/`

使用的 MCP 工具/命令：

- `brief`
- `plan_task`
- `worktree_guard`
- `agent_board_claim / heartbeat / snapshot`
- `memory_search`
- `code_explore`
- `code_node`
- `routes`
- `capabilities`
- `db_schema`
- `probe`
- `call_capability`
- `tail_log`
- `finish_task`
- `memory_write`
- `mcp_feedback`
- 本地只读命令：`sed`、`find`、`wc`、`test`

活系统只读证据：

- `/api/health` 返回 `status: ok`，worker running，注册 handler 包含 `agent_context_compact`、`agent_execute_slow_tool`、`memory_*`、`kb_*`、`workflow_mine`。
- `/api/agent/health` 返回 `module: agent, status: ok`。
- `/api/agent/workflows?limit=5` 返回 `items: [], total: 0`。
- `agent:list_workflows` capability 返回 `items: [], total: 0`。
- `memory:overview_stats` 返回 memory/experience 均为 0，说明当前产品内记忆数据未沉淀到可复用规模。
- `knowledge:get_pending_count` 返回 `pending_count: 2`，说明知识库有待处理治理项。

对标的外部项目/资料：

- 本机资料：`/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms/openclaw/README.md`
- 本机资料：`/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms/openclaw/docs/agent-runtime-architecture.md`
- 本机资料：`/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms/openclaw/docs/openclaw-agent-runtime.md`
- 本机资料：`/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms/openclaw/qa/maturity-scores.yaml`
- 子代理只读参考：OpenCode、OpenHands、LangGraph、Dify、Hermes-agent、mini-SWE-runner 等本机参考目录。
- 官方资料：Claude Code docs `https://code.claude.com/docs/en/overview`
- 官方资料：OpenCode docs `https://opencode.ai/docs/agents/`
- 官方资料：Aider git docs `https://aider.chat/docs/git.html`
- 官方资料：Cursor Agent best practices `https://cursor.com/blog/agent-best-practices`
- 官方资料：Devin docs `https://docs.devin.ai/get-started/devin-intro`
- 官方资料：OpenHands SDK `https://docs.openhands.dev/sdk/getting-started`
- 官方资料：SWE-agent ACI `https://github.com/SWE-agent/SWE-agent/blob/main/docs/background/aci.md`
- 官方资料：LangGraph overview/persistence/interrupts `https://docs.langchain.com/oss/python/langgraph/overview`
- 官方资料：AutoGen AgentChat `https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html`
- 官方资料：CrewAI Flows `https://docs.crewai.com/en/concepts/flows`
- 官方资料：Open WebUI Knowledge `https://docs.openwebui.com/features/workspace/knowledge/`
- 官方资料：AnythingLLM Agents `https://docs.anythingllm.com/agent/overview`
- 官方资料：VS Code Tasks `https://code.visualstudio.com/docs/debugtest/tasks`
- 官方资料：JetBrains Plugin SDK `https://plugins.jetbrains.com/docs/intellij/plugin-configuration-file.html`
- 官方资料：Obsidian Plugin Docs `https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin`

## 3. 当前 Agent 能力地图

### 任务理解

已有能力：

- Agent 有 `intent_preflight`、`understanding_loop`、thinking level signals、profile/enterprise/role/market 四维画像。
- context pipeline 会注入 system prompt、技能、记忆、经验、workflow recipe。

缺口：

- understanding 默认不是强制主链。
- 用户目标、约束、验收标准还没有稳定转成 workflow plan。
- 缺少“需求不清时必须确认 / 低风险时自动推进”的统一决策器。

### 规划拆解

已有能力：

- `agent_workflow_runs`、`agent_workflow_steps` 可记录任务和阶段。
- `workflow_service` 支持 run/step 创建、状态推进、终态裁判。

缺口：

- 缺少成熟 planner/executor/state machine。
- 缺少 recipe/node/edge/condition/retry policy。
- chat 主链没有默认自动生成 plan 和 step。

### 工具使用

已有能力：

- 渐进式工具发现只暴露 `skill_list / skill_describe / skill_use` 三个元工具，避免工具列表随模块膨胀。
- `tool_discovery.py` 经 capability registry 调模块能力。
- `tool_orchestrator.py` 对读工具并发、写/破坏性工具串行，未知工具保守串行。
- `ToolGate` 校验工具名，慢工具投 `SystemTaskQueue`。

缺口：

- 工具失败后的重试策略、替代工具、降级路径还不够结构化。
- 代码任务缺少固定 ACI：`code_explore -> read_slice -> patch -> diff -> test -> summarize`。
- capability metadata、side effect、approval policy 还没有统一产品化展示。

### 上下文管理

已有能力：

- `context_pipeline.run_pipeline` 分阶段处理事件投影、tool result reducer、thinking routing、system prompt、ready compaction、技能注入、预算装配、记忆/经验/workflow recipe 注入。
- `agent_context_compactions` 和 `agent_events` 支持压缩与回放。
- tool result 压缩、预算守卫和最新用户目标 pinning 已实现。

缺口：

- checkpoint 默认关闭。
- 长任务跨中断恢复还没有成为默认用户体验。
- 模型选择、预算策略、上下文压缩策略未按任务类型系统化。

### 记忆复用

已有能力：

- `layered_memory.py` 通过 `call_capability("memory", ...)` 调 stable rules、chunk、semantic recall。
- `experience_memory.py` 支持成功经验保存、匹配、反馈。
- 记忆质量记录写原子文件，避免纯内存。
- memory 模块提供 `save/recall/fuse/dream/save_experience/match_experience/recall_stable_rules/recall_chunk` 等能力。

缺口：

- 当前活系统 `memory:overview_stats` 为 0，说明产品内长期记忆和经验尚未形成规模。
- 项目工具台 Markdown 项目记忆与产品内 memory 模块是两套世界，缺映射或同步策略。
- review fork 能提出 memory/skill/profile 建议，但还没成为稳定自优化闭环。

### 工作流持久化

已有能力：

- `workflow_models.py` 定义 run/step/tool/artifact/verification/failure。
- `agent_approval_queue` 已扩展 workflow_run_id、workflow_step_id、tool_call_id、payload_hash、resume_target。
- `agent_checkpoints` 已扩展 workflow_run_id、workflow_step_id、agent_run_id、checkpoint_type、resume_cursor。
- `finalize_workflow` 要求至少一条 verification，且 `PASS_WITH_DEBT` 进入 `partial`。

缺口：

- workflow ledger 目前更像可用账本，还不是所有 Agent 任务的默认 truth source。
- 当前活系统 workflow 列表为空，说明真实用户任务未沉淀到 workflow。
- `RuntimePolicy.enable_checkpointer=False`，恢复能力存在但默认不启用。

### 审批与安全

已有能力：

- `action_policy.py` 有敏感工具名单、系统 principal hard block、参数脱敏、approval queue。
- workflow 审批保存 payload_hash/resume_target，拒绝后写 verification/failure 并终止。
- terminal-tools 与 desktop-tools 文档上区分工作区草稿和框架文件系统。

缺口：

- 普通审批 UI 展示风险信息不足，后端字段未充分呈现。
- 需要声明式权限 DSL：工具、路径、命令、模块、MCP server、agent 类型的 `allow/ask/deny`。
- 子代理提到 terminal-tools 代码已有 macOS sandbox-exec/fail-closed，文档仍偏“应用层约束”，需要另行同步口径。

### 多 Agent 协作

已有能力：

- `agent:spawn_subagent` 支持单任务/批量、工具白名单、写保护、上下文压缩、轨迹记录。
- `agent_trajectory_records` 能沉淀执行轨迹。

缺口：

- 缺 work item、lane、claim/release、lease、stale 回收、依赖图、结果 schema、review gate。
- 子 Agent 结果没有统一合并裁判和冲突解决。
- 缺多 Agent 可视化工作台。

### 产物生成

已有能力：

- workflow artifact ledger 可记录 artifact_type、storage_kind、storage_ref、visibility、lifecycle、checksum。
- 框架已有 Content IR、office-gen、文件发布、artifact service。

缺口：

- artifact ledger 未变成用户默认产物卡片。
- 缺预览、打开、版本、下载、发布、撤销、重新生成、回滚。
- 终端工作区草稿到桌面文件系统的 publish 闭环还应自动进入 workflow artifact + verification。

### 自我纠错

已有能力：

- stuck detector 检测重复工具、重复错误、空响应。
- inline tool recovery、tool intent retry、fallback chain 兼容壳、failure diagnostics 已有。
- workflow failure records 可记录 failure_type、error_signature、retryable、next_action。

缺口：

- stuck 后更多是报错停止，缺自动重规划。
- 缺“失败归因 -> 换模型/换工具/缩小目标/请求用户确认/转人工”的状态机。
- 缺 Problem Matcher 把测试/日志/终端输出变成结构化问题。

### 用户无感知

已有能力：

- 对话内有“正在工作/已工作”折叠组。
- workflow summary 对普通用户隐藏开发细节。
- 慢工具和后台任务可投队列。

缺口：

- 用户还需要理解“工作流/工具记录/已工作”等技术词。
- `manual_required`、`partial` 缺用户下一步动作。
- 通知中心、任务中心、Agent workflow、产物发布未形成一体化体验。

### 可观测性

已有能力：

- `agent_events`、`agent_message_meta.timeline`、`agent_trajectory_records`、`agent_failure_records`、`agent_verification_results`、admin overview/replay/snapshots/failure diagnostics。
- dev_toolkit 有 release gate、smoke、sandbox matrix、agent board、memory、mcp feedback。

缺口：

- 成本、耗时、错误、瓶颈还没有统一进入用户级 workflow dashboard。
- trace/run/step/tool/result 没有像 LangSmith、Dify logs、VS Code Problems 那样产品化。
- 管理员视图偏账本，不够像“诊断控制台”。

## 4. 评分表

| 维度 | 分数 | 证据 |
|---|---:|---|
| 任务理解 | 6.5 | 有 intent preflight、understanding loop、画像和上下文注入，但未强制把用户目标转成 plan/验收。 |
| 规划拆解 | 5.0 | 有 workflow step ledger，但缺自动 planner、节点图、条件分支和依赖。 |
| 工具使用 | 7.5 | 元工具发现、ToolGate、ToolOrchestrator、capability registry 已成型。 |
| 上下文管理 | 7.0 | 事件投影、预算、压缩、tool result reducer、记忆/经验注入都有。 |
| 记忆复用 | 6.5 | 三层记忆和经验接口完整，但活系统 memory/experience 当前为 0，真实复用不足。 |
| 工作流持久化 | 6.5 | workflow 表/API/capability 完整，chat 主链尚未默认绑定，checkpoint 默认关闭。 |
| 审批与安全 | 7.0 | action policy、approval queue、payload_hash、resume_target 具备；审批 UI 和权限 DSL 不足。 |
| 多 Agent 协作 | 5.5 | 有 `spawn_subagent`，缺 work item、lane、claim、合并裁判。 |
| 产物生成 | 5.5 | artifact ledger 存在，缺默认产物工作台和发布/回滚闭环。 |
| 自我纠错 | 6.0 | 有 stuck、inline retry、failure records，缺重规划和 Problem Matcher。 |
| 用户无感知 | 6.5 | 折叠 timeline 和极简 workflow summary 已有，普通用户动作闭环不足。 |
| 可观测性 | 7.0 | events/meta/trajectory/admin 较全，仍缺统一 trace/problem/cost 控制台。 |

综合评分：**6.4/10**。

## 5. 对标成熟系统差距

### Coding Agent

代表：Claude Code、OpenCode、Aider、Cursor Agent、Windsurf。

成熟做法：

- repo 理解有 repo map、符号索引、project instructions、打开文件/终端上下文。
- 文件编辑有 diff、snapshot、undo、checkpoint、message-scoped revert。
- 安全有 plan/build 模式、工具权限 allow/ask/deny、hooks、规则文件。
- 测试闭环把 lint/test/build 作为自动目标。
- 长任务支持 resume、context compaction、worktree 并行、分支/PR 交付。

V2 差距：

- CodeGraph/codemap 很强，但还是项目工具台能力，未成为 Agent 自动内循环。
- 缺 message-scoped diff/revert、branch/PR 交付、trajectory inspector。
- 缺代码任务专用 ACI，terminal-tools 仍偏通用命令兜底。

### 自主软件工程 Agent

代表：Devin、OpenHands、SWE-agent。

成熟做法：

- 独立 workspace/VM/container/backend。
- 任务源接 GitHub/Jira/Linear/Slack。
- 浏览器、终端、编辑器、测试、部署协同。
- 以 branch/PR/artifact 为交付单元。
- trajectory 可 inspect/replay。

V2 差距：

- V2 明确不追 Docker 强隔离，这是局域网取舍，不算错误；但对标 Devin/OpenHands 时，隔离和远程长任务能力不同。
- 浏览器/终端/桌面/问题面板还没有组合成一个“执行环境”。
- 交付单元仍偏对话结果和文件产物，不是默认 branch/PR/release gate。

### Workflow / 多 Agent 框架

代表：LangGraph、AutoGen、CrewAI、Dify workflow。

成熟做法：

- LangGraph 用 StateGraph、checkpoint、store、interrupt、time travel。
- Dify workflow 有节点、条件、人工输入、日志。
- AutoGen/CrewAI 有 Agent/Team/Crew/Task/Flow、角色、终止条件、输出 schema。
- 人工审批不是简单弹窗，而是保存 payload、resume cursor、原动作上下文。

V2 差距：

- V2 有 workflow ledger，但缺 workflow recipe/node/edge/condition/retry policy。
- 多 Agent 仍偏 spawn，不是 team/work queue。
- 审批后恢复能力后端不错，但主链应用范围还不够。

### 本地 AI 工作台 / 知识库产品

代表：Open WebUI、AnythingLLM、Dify knowledge。

成熟做法：

- 知识库不仅有 semantic search，还有 BM25、向量、rerank、全文、目录、分页阅读、引用证据。
- 多模型配置、用户权限、工作区、工具和知识源被产品化。
- Agent 可用 agentic retrieval：grep/view_file/query，而不是只问一个 search。

V2 差距：

- knowledge 模块本身强，但 Agent 可用工具还应补 `tree/list/grep/read_lines/citation_bundle`。
- memory 与 knowledge、项目记忆、文件引用的用户级统一体验不足。
- 知识治理状态还未完全进入 Agent 工作流。

### IDE / 桌面任务系统

代表：VS Code tasks/problem matcher、JetBrains AI、Obsidian 插件生态。

成熟做法：

- VS Code tasks 把任务输出解析成 Problems，定位 file/line/severity/message。
- 插件生态靠 manifest 声明 commands/actions/settings/contribution points/permissions/version compatibility。
- 用户看到问题面板和任务状态，开发者看到完整日志。

V2 差距：

- release gate、lint、probe、terminal 输出还没有统一 problem matcher。
- 模块 manifest 主要声明入口和 public actions，尚未扩展成完整 contribution points。
- Agent 工作结果没有统一进入“问题面板/产物面板/任务面板”。

## 6. 当前已有优势

1. **架构边界清楚**：模块间 100% 走 capability，Agent 不直接 import memory/knowledge。
2. **工具发现路线正确**：三个元工具避免 token 随模块数量膨胀。
3. **workflow ledger 设计方向正确**：run/step/tool/artifact/verification/failure 加 approval/checkpoint 关联，是工作中枢该有的骨架。
4. **终态裁判意识强**：`finalize_workflow` 不允许无 verification 终态，`PASS_WITH_DEBT` 不算 clean completed。
5. **记忆体系分层**：static/stable rules/chunk/semantic/experience 的方向成熟。
6. **安全边界有工程落点**：action policy、脱敏、系统 principal hard block、terminal/desktop 两套世界分离。
7. **项目工具台很强**：brief/plan/worktree/codegraph/routes/capabilities/db_schema/probe/run_test/finish_task/memory/feedback 让开发 Agent 有成熟操作面。
8. **多 worker 风险已有意识**：许多共享状态开始落 DB 或原子文件。
9. **文档把边界讲透**：模块边界、Content IR、任务队列、测试铁律较清楚。
10. **能对接成熟外部思想**：现有 ledger 与 LangGraph/Dify/VS Code problem matcher 的方向兼容。

## 7. 当前关键短板

1. **workflow 未默认接入对话主链**：这是从“底座”到“中枢”的最大差距。
2. **planner 不够一等**：缺少稳定图定义、节点依赖、条件分支、节点重试、timeout/backoff。
3. **verification 还偏记录层**：需要自动跑验证、解析失败、回到修复循环。
4. **多 Agent 缺治理协议**：子 Agent 有能力，缺任务池和合并裁判。
5. **记忆数据未形成规模**：当前 live memory overview 为 0。
6. **审批 UI 信息不足**：admin 可能看不到风险等级、影响范围、payload hash、resume target。
7. **产物闭环不完整**：artifact 没有默认用户操作路径。
8. **Problem Matcher 缺位**：日志/test/probe/terminal 输出还未结构化为可定位问题。
9. **权限策略不够声明式**：敏感名单存在，但缺全局可配置 allow/ask/deny。
10. **产品内 memory 和项目记忆割裂**：dev_toolkit Markdown 记忆非常有价值，但产品 Agent 不自然复用。

## 8. 下一轮能力升级路线图

### 第 1 阶段：低冲突快补

目标：不抢正在进行的 Agent workflow 实现，把“已落地能力”补成更可用、更安全、更可观察。

建议任务：

1. 审批面板增强：展示 risk_level、decision_scope、payload_hash、resume_target、参数摘要、影响范围。
2. Workflow detail 用户视图增强：普通用户看到 plan/doing/verify/publish 四段式摘要，admin 再看细账本。
3. terminal-tools 文档口径同步：核实 sandbox-exec/fail-closed 与 README/开发文档一致。
4. 记忆状态治理：把 memory overview、经验为空、项目记忆割裂作为可见诊断。
5. Agentic Knowledge 快补：新增只读 `tree/list/grep/read_lines/citation_bundle` 能力建议，不改主 workflow。

依赖关系：多数可以在 Agent workflow 中枢任务完成后做；审批 UI 和文档同步可并行，但要避免改同一批 `Workflow*.vue` 文件。

### 第 2 阶段：Agent 中枢增强

目标：让每个较长用户任务自动进入 workflow run，工具调用和验证成为默认账本。

建议任务：

1. tool loop 自动绑定 workflow：创建 run/step，工具调用落 `agent_tool_calls`，结果写 `result_ref`。
2. verification 自动编排：按任务类型自动跑 lint/test/probe/read-back，结果写 `agent_verification_results`。
3. Problem Matcher：解析 pytest/ruff/npm/probe/terminal 输出为结构化 problems。
4. stuck recovery state machine：重复工具/错误后自动换策略、缩小目标、请求确认或转人工。
5. workflow recipe：先做 schema 和少量内置 recipe，不做可视化编排器。

依赖关系：必须等“后端无感 Agent 工作流中枢完整落地”稳定后再做，否则会直接抢 `modules/agent/backend/services/workflow_service.py`、`handlers/workflow.py`、`frontend/components/Workflow*.vue`。

### 第 3 阶段：多 Agent / 自主工作台

目标：从单 Agent 工作流升级为可派发、可追踪、可合并、可审计的多 Agent 工作台。

建议任务：

1. `agent_work_items`：task、owner、role、tool_scope、lease、status、result_schema、review_status。
2. 多 Agent lane：planner、executor、reviewer、verifier 分工。
3. 合并裁判：冲突检测、边界检查、verification gate、人工 review。
4. 产物工作台：artifact preview/version/publish/revert/download。
5. 插件/模块贡献点扩展：commands/actions/settings/permissions/version compatibility。

依赖关系：依赖第 2 阶段的 workflow 主链和 Problem Matcher，否则多 Agent 只会放大不可观测和不可恢复问题。

## 9. 后续执行信建议

### 执行信 1：Agent 工具调用可靠性与失败恢复专项

目标：把工具调用从“能调”升级为“可落账、可重试、可解释失败、可验证完成”。

边界：

- 优先改 `modules/agent/backend/runtime/`、`modules/agent/backend/engine/`、`modules/agent/backend/services/`。
- 若 workflow 主链任务尚未合并，只写调研/设计或等待，不抢 `workflow_service.py`。

禁止范围：

- 禁止改 `backend/app/`。
- 禁止直接改 memory/knowledge/terminal-tools 业务逻辑。
- 禁止把工具失败包成成功。

验收方式：

- 单测覆盖 tool failure normalization、stuck recovery、tool call ledger、verification 写入。
- 活系统用只读/低副作用 capability 验证。
- 必须证明失败能进入 failure record 或 manual_required，而不是静默消失。

与当前并行任务关系：

- **依赖 Agent 工作流中枢完成**。若中枢未完成，只能先做 runtime 失败分类，不碰 workflow 接入。

### 执行信 2：Agent 上下文与记忆复用专项

目标：让 Agent 稳定复用 static memory、stable rules、chunk、semantic memory、experience、项目记忆，并能解释召回质量。

边界：

- `modules/agent/backend/engine/layered_memory.py`
- `modules/agent/backend/engine/experience_memory.py`
- `modules/memory/`
- 必要时只增 capability，不直接读表。

禁止范围：

- 禁止让 Agent 直接读写 memory 表。
- 禁止把每个 workflow step 都写项目记忆。
- 禁止污染真实用户记忆。

验收方式：

- 构造可清理的测试记忆，验证 recall/experience/stable rule 注入。
- 验证 recall quality 记录跨 worker 可见。
- 活系统 `memory:overview_stats` 能反映测试数据，测试后清理。

与当前并行任务关系：

- 可与数据库反向链路任务有轻微交集，需避开其 release gate/task queue 改动。
- 不依赖 Agent workflow 中枢，但若要把记忆写入 workflow artifact，则应等中枢完成。

### 执行信 3：多 Agent 派发、跟踪、合并专项

目标：把 `spawn_subagent` 升级为可治理的多 Agent work item 系统。

边界：

- `modules/agent/backend/`
- `modules/agent/frontend/`
- 新增 Agent 自有表必须 `agent_*` 前缀。

禁止范围：

- 禁止改其他模块业务表。
- 禁止引入直接跨模块 import。
- 禁止先做复杂可视化编排器。

验收方式：

- 支持创建 work item、claim、heartbeat、complete/block、stale reclaim。
- 子 Agent 有 role/tool scope/result schema。
- reviewer gate 能合并多个子任务结果并记录 conflicts/debts。

与当前并行任务关系：

- **强依赖 Agent workflow 中枢完成**。否则多 Agent 没有统一账本，会和当前 workflow 实现冲突。

### 执行信 4：Agent 用户无感工作痕迹与进度反馈专项

目标：把“已工作/工作流/审批/产物/失败”打磨成普通用户看得懂的状态体验。

边界：

- `modules/agent/frontend/`
- `modules/agent/backend/handlers/workflow.py` 的最小 API 补充。

禁止范围：

- 禁止修改框架桌面壳 `frontend/src/`。
- 禁止重做复杂项目管理 UI。

验收方式：

- 普通用户只看极简进度、下一步、产物。
- admin 可展开 steps/tools/verifications/failures。
- `partial/manual_required/needs_confirmation` 都有明确下一步动作。

与当前并行任务关系：

- 依赖 Agent workflow 中枢完成后再做，避免抢 `Workflow*.vue`。

### 执行信 5：Agent 产物发布与桌面/文件闭环专项

目标：把 workflow artifact 变成可预览、可下载、可发布、可回滚的产物路径。

边界：

- `modules/agent/`
- 可调用框架 `content:*`、`desktop-tools:*`、`terminal-tools:publish` 等公开能力。

禁止范围：

- 禁止直接创建/替换框架物理文件。
- 禁止绕过 `check_file_access`。
- 禁止修改 Content IR 框架层，除非另开框架任务。

验收方式：

- 产物写入 artifact ledger。
- 用户能从 workflow detail 打开/预览/下载/发布。
- 发布前必须有 verification。

与当前并行任务关系：

- 依赖 Agent workflow 中枢；如涉及文件/发布治理，需等数据库反向链路主链路闭环完成。

## 10. 不建议现在做的事

1. 不建议现在做大型可视化 workflow 编排器。先补 recipe/node/edge schema 和执行语义。
2. 不建议改框架 `framework_workflow_*` 来承载 Agent 业务。当前 Agent 自有 ledger 路线正确。
3. 不建议追 Docker 强隔离作为主线。项目已明确局域网应用层边界取舍，应继续把边界实现好。
4. 不建议把所有工具过程都写项目记忆。每个 workflow 最多一条 summary memory 更合理。
5. 不建议把多 Agent 做成聊天房。应先做 work item、role、tool scope、result schema。
6. 不建议为了评分好看清理历史数据或假装 clean。债务要结构化，不要伪装。
7. 不建议让 Agent 直接读写其他模块表。跨模块规则必须继续坚持。
8. 不建议在 workflow 主链未稳定前叠加自动发布、自动 push、自动删除等高风险能力。

## 11. 剩余风险

1. 当前工作区有大量并行任务未提交改动，本报告只读调研，未验证这些改动最终合并后的代码状态。
2. 活系统 workflow 当前为空，无法基于真实历史 workflow 数据评估用户体验，只能评估能力底座和 API 可用性。
3. 外部对标以本机参考资料和公开文档为主，没有下载新的完整项目到本项目目录。
4. memory live overview 为 0 可能受当前环境/owner/初始化状态影响，但仍足以说明“真实经验复用规模不足”这个风险。
5. 子代理指出 terminal-tools 代码与文档安全口径可能不一致，本报告未深挖实现细节，建议后续专项复核。
6. 当前评分是架构成熟度和活系统信号的综合判断，不等于功能 bug 数量审计。
