# 后端无感 Agent 工作流中枢调研报告

## 1. 一句话结论

华世王镞 V2 应该在 `modules/agent` 内建设一个新的、持久化的 Agent 工作流中枢，用新表记录 `WorkflowRun / Step / ToolCall / Artifact / Approval / Verification` 等核心状态，`framework_system_task_queues` 只作为后台执行队列复用，不承载用户可见工作流真相；前台只显示极简状态，危险动作才打断确认，所有跨模块能力继续走统一 capability 通路。

最小可落地版本不是“可视化工作流平台”，而是一个能把 Agent 后台任务可靠推进到明确终态的控制面：可恢复、可审计、可暂停确认、可验证、可解释失败、可治理产物和记忆。

## 2. 我们真正要解决的问题

当前系统已经有 Agent 模块、任务队列、模块能力调用、MCP 工具台、项目记忆、投递信、release gate、sandbox matrix、desktop shell、knowledge / memory / codemap、terminal-tools / browser-tools 等能力，但它们更像一组强工具，而不是一个对用户无感的后台中枢。

真正的问题不是“缺一个 UI”，而是缺少一个统一的运行账本和裁判层：

1. 用户任务缺少统一终态：做完、失败、部分完成、需要确认、带债完成之间没有足够稳定的状态定义。
2. 后台工具调用缺少用户级串联：`SystemTaskQueue` 可以跑任务，但不能自然表达“这次用户目标推进到了哪一步”。
3. Agent 行为缺少全局恢复策略：工具失败、MCP 断开、进程重启、worker 切换、dirty worktree、release gate 债务，都需要被纳入同一个 run。
4. 用户被迫看太多细节：哪个 agent、哪个 MCP、哪个测试、哪个队列行，本应是开发者或管理员视角。
5. 产物和记忆容易膨胀：每一步日志、截图、临时文件、记忆写入都可能堆积成噪声。
6. 多 worker 下纯内存状态不可靠：任务状态、锁、重试、审批、checkpoint、工具调用归属都必须持久化。

本次调研建议把“后台无感 Agent 工作流中枢”定义为三层：

1. 用户层：只暴露极简状态、确认请求、最终产物。
2. 控制层：持久化 WorkflowRun、Step、Approval、Verification、Artifact、Failure。
3. 执行层：复用现有 `framework_system_task_queues`、Agent runtime、module capabilities 和各工具模块。

## 3. 用户无感前台模型

前台应该只理解 6 个状态：

| 状态 | 用户含义 | 后台真实含义 |
|---|---|---|
| 等待中 | 任务已接收，还没开始或排队中 | `WorkflowRun` 已创建，等待队列 worker 或审批前置条件 |
| 处理中 | 后台正在推进 | 可能包含规划、查代码、运行工具、测试、生成产物、自动重试 |
| 需要确认 | 系统需要用户做一个明确决定 | 危险动作、外部发布、提交推送、大额删除、权限变更、无法自动裁决 |
| 已完成 | 目标完成且验证通过 | 所有必要步骤终态完成，最终 `VerificationResult` 为 pass |
| 失败 | 自动推进无法继续 | 超过重试次数、遇到禁止动作、验证失败且无法自动修复 |
| 部分完成 | 有产物或部分修复，但未达到干净完成 | release gate 为 `PASS_WITH_DEBT`、部分子任务失败、缺确认、未提交等 |

用户什么时候应该看到通知：

1. 任务已接收：短通知，确认系统已接管。
2. 进入需要确认：强通知，需要用户决策。
3. 已完成并有产物：普通通知，带打开产物入口。
4. 失败或需人工介入：强通知，带简短原因和下一步。
5. 长任务超过阈值：弱通知，例如“仍在处理中，已完成 3/5 个阶段”，不展示工具细节。

用户什么时候应该被打断确认：

1. 会产生不可逆或难恢复副作用。
2. 会触达外部系统或真实用户。
3. 会修改权限、账号、安全策略、密钥、生产数据。
4. 会提交、推送、创建 PR、发布到桌面文件系统或覆盖用户文件。
5. 会发生大范围删除、批量重命名、跨工作区移动。
6. release gate 是 `PASS_WITH_DEBT`，但系统准备把它当作正式完成交付时。

哪些过程应该完全后台静默：

1. 读文件、查文档、查 CodeGraph / codemap。
2. 拆任务、生成内部计划。
3. 调用 knowledge / memory 做检索。
4. 运行 lint、类型检查、定向测试、probe。
5. 自动重试临时失败的只读工具。
6. 生成草稿、整理日志、创建临时 artifact。
7. 上下文压缩、checkpoint、事件落库。

哪些细节只给开发者或管理员看：

1. agent 名称、模型、token、上下文长度。
2. MCP 工具调用明细、参数、返回值。
3. 队列行、worker、重试堆栈、异常 traceback。
4. release gate 细项、sandbox matrix 原始输出。
5. dirty worktree 文件清单、锁等待原因。
6. 被脱敏后的 tool arguments、审批 payload hash。

“已工作时间线”建议默认折叠。用户只看到一行摘要，例如：

```text
已完成：分析代码、生成报告、验证边界。详情可展开。
```

只有以下情况默认展开到“简明时间线”：

1. 失败。
2. 需要确认。
3. 部分完成。
4. 用户手动选择“查看详情”。

即使展开，也不默认显示全部 tool log，只显示用户可理解的阶段：接收、分析、执行、验证、产物、结束。完整事件流留给开发者/管理员。

## 4. 后端核心对象设计

结论：需要新建持久化数据模型，不应复用 `framework_system_task_queues` 作为主模型。

`framework_system_task_queues` 适合做执行队列：排队、抢占、重试、超时恢复、worker 消费。它不适合做用户级 workflow ledger，因为它无法稳定表达多 step、多 agent、多 tool、多 artifact、多 approval、多 verification 的全链路关系。

建议第一阶段把核心表建在 `modules/agent` 内，例如以 `agent_workflow_*` 或 `agent_*` 前缀命名。框架层只提供现有公共能力：任务队列、能力注册、通知、文件/内容、数据库连接、模型网关。不要为了 Agent 中枢先把框架变成通用 workflow 平台。

### WorkflowRun

用途：用户任务的顶层运行账本，是前台极简状态的唯一来源。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` | workflow run id |
| `owner_id` / `creator_id` | 用户或系统发起者 |
| `source` | chat、scheduler、mailbox、manual、system |
| `title` / `intent` | 用户目标摘要和原始意图 |
| `status` | waiting、processing、needs_confirmation、completed、failed、partial、cancelled |
| `terminal_status` | clean_completed、completed_with_debt、failed_verified、manual_required、cancelled |
| `verification_status` | pending、pass、fail、debt、skipped |
| `current_step_id` | 当前可见阶段 |
| `progress_summary` | 给用户看的短摘要 |
| `developer_summary` | 给开发者看的内部摘要 |
| `dirty_worktree_state` | start_clean、start_dirty、became_dirty、external_dirty、resolved |
| `release_gate_verdict` | pass、fail、pass_with_debt、not_run |
| `queue_task_ids` | 关联的 `framework_system_task_queues.id` 列表或 JSON |
| `artifact_summary` | 最终产物摘要 |
| `started_at` / `finished_at` / `updated_at` | 时间 |

生命周期：

```text
created -> waiting -> processing -> needs_confirmation -> processing -> completed
                                      -> failed
                                      -> partial
                                      -> cancelled
```

和 `framework_system_task_queues` 的关系：一对多。Run 可以派发多个 queue task；queue task 只负责执行某个后台片段，不能决定 Run 的最终用户语义。

是否需要持久化：必须。

是否需要跨 worker 一致：必须。所有状态变更通过 DB 事务或等价持久化机制完成。

### WorkflowStep

用途：表达一个 run 内的阶段，连接用户可理解的阶段和后台执行细节。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` | step id 和所属 run |
| `step_key` | stable key，例如 `plan`、`code_explore`、`edit`、`verify`、`publish` |
| `title` | 用户或开发者可读标题 |
| `type` | plan、agent、tool、verification、approval、artifact、memory、publish |
| `status` | pending、running、paused、completed、failed、skipped |
| `order_index` | 展示和执行顺序 |
| `input_ref` / `output_ref` | 指向 artifact、checkpoint 或 JSON 摘要 |
| `retry_count` / `max_retries` | step 级重试 |
| `error_class` / `error_signature` | 失败分类和去重 |

生命周期：随 Run 创建或动态追加；每个 Step 必须进入 completed、failed、skipped 或 cancelled。

和队列关系：Step 可对应 0 个、1 个或多个 queue task。只读规划 step 可以同步完成；长工具 step 走队列。

是否持久化：必须。

跨 worker 一致：必须。

### Subtask

用途：表达由 Agent 拆出的子目标，不一定直接等于 Step。Step 更偏执行阶段，Subtask 更偏目标分解。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` | 子任务归属 |
| `parent_subtask_id` | 子任务树 |
| `title` / `acceptance_criteria` | 子任务目标和验收标准 |
| `assigned_agent` | 负责的 agent 或 lane |
| `status` | pending、running、completed、failed、blocked、cancelled |
| `depends_on` | 子任务依赖 |
| `result_summary` | 子任务结果摘要 |

生命周期：规划时生成，执行中可拆分或合并。终态必须被 Run 收敛。

和队列关系：Subtask 不直接等于队列任务，通常由 AgentRun 或 WorkflowStep 执行。

是否持久化：建议必须，至少从 Phase 2 开始必须。

跨 worker 一致：必须，否则多 agent 分工会乱。

### AgentRun

用途：记录一次模型/agent 执行尝试，区别于用户级 WorkflowRun。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` | 归属关系 |
| `agent_code` | agent 标识 |
| `model` / `policy` | 模型和执行策略 |
| `conversation_id` | 对话或事件流 |
| `checkpoint_id` | 关联 checkpoint |
| `status` | running、paused、completed、failed、interrupted |
| `token_usage` / `cost_estimate` / `duration_ms` | 观测指标 |
| `stop_reason` | completed、tool_error、approval_required、context_limit、manual_stop |

生命周期：每次 Agent 进入 tool loop 或后台执行时创建；进程丢失时应结算为 `interrupted`，不要假装仍在 running。

和队列关系：一个 queue task 可能启动一个 AgentRun。AgentRun 要保存 `queue_task_id` 作为关联。

是否持久化：必须。现有 `agent_checkpoints` 和 `agent_events` 可复用，但需要 run 级索引。

跨 worker 一致：必须。

### ToolCall

用途：持久化每一次工具或 capability 调用，解决副作用、重试、审批、审计问题。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` / `agent_run_id` | 归属 |
| `tool_name` | 工具名 |
| `capability_key` / `action` | 统一 capability 路径 |
| `caller` | user/system/agent |
| `arguments_ref` | 脱敏后的参数引用 |
| `arguments_hash` | 审批绑定和幂等判断 |
| `side_effect_level` | readonly、workspace_write、user_file_write、external_side_effect、dangerous |
| `approval_policy` | auto、requires_user、requires_admin、blocked |
| `status` | planned、waiting_approval、running、completed、failed、interrupted、blocked |
| `idempotency_key` | 防重复执行 |
| `result_ref` | 输出引用 |
| `error_class` / `error_signature` | 失败分类 |

生命周期：

```text
planned -> waiting_approval -> running -> completed
                         -> rejected
planned -> blocked
running -> failed / interrupted
```

和队列关系：慢工具可转成 queue task；ToolCall 是语义账本，queue task 是执行载体。

是否持久化：必须。

跨 worker 一致：必须。尤其是有副作用的工具调用必须有幂等键和最终状态。

### Artifact

用途：统一记录 workflow 产生或引用的产物，不重复存大内容，优先链接现有 Content IR、Resource、framework artifact、桌面发布文件、工作区临时文件。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` | 归属 |
| `artifact_type` | report、patch、test_result、screenshot、document、spreadsheet、log、temp_file |
| `storage_kind` | content_package、framework_artifact、resource、desktop_file、workspace_temp、external_url |
| `storage_ref` | 对应 id 或路径 |
| `visibility` | user、developer、admin、internal |
| `lifecycle` | temp、candidate、published、archived、expired |
| `ttl` | 自动清理时间 |
| `checksum` | 去重和完整性 |
| `summary` | 用户可见摘要 |

生命周期：创建为 temp/candidate；用户确认或 workflow 完成后部分转 published；临时产物 TTL 清理。

和队列关系：queue task 可能生成 artifact，但 artifact 属于 WorkflowRun。

是否持久化：必须持久化元数据；内容按类型存现有系统。

跨 worker 一致：必须。

### Checkpoint

用途：保存可恢复状态，避免进程重启、worker 切换、MCP 断开后丢失上下文。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` / `agent_run_id` | 归属 |
| `checkpoint_type` | workflow、agent_loop、tool_pending_write |
| `state_ref` | JSON 状态或大对象引用 |
| `resume_cursor` | 恢复位置 |
| `pending_writes` | 已规划但未最终提交的写入或工具结果 |
| `created_at` | 时间 |

生命周期：关键节点前后保存；Run 终态后保留审计期限，之后压缩或归档。

和队列关系：worker 领取 queue task 后先读 checkpoint；失败或中断时写回 checkpoint。

是否持久化：必须。现有 `agent_checkpoints` 可作为 Agent loop 的基础，workflow 级还需要更清晰的归属。

跨 worker 一致：必须。

### ApprovalRequest

用途：表达需要用户或管理员确认的暂停点。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` / `tool_call_id` | 归属 |
| `request_type` | git_commit、publish_file、external_call、delete、permission_change、release_with_debt |
| `risk_level` | low、medium、high、critical |
| `decision_scope` | once、same_payload、same_run、policy_update |
| `payload_snapshot_ref` / `payload_hash` | 绑定确认内容，防止确认后参数变更 |
| `status` | pending、approved、rejected、expired、cancelled |
| `requested_by` / `decided_by` | 发起和决策者 |
| `expires_at` | 过期时间 |
| `resume_target` | 审批后恢复哪个 run/step/tool |

生命周期：创建后 Run 进入 `needs_confirmation`；批准后恢复；拒绝后进入 failed 或 partial；超时按策略处理。

和现有 `agent_approval_queue` 的关系：第一阶段可以复用或包一层现有审批表，但需要新增 workflow 关联字段和恢复目标。不要只给模型返回 `approval_required`，必须能恢复原 tool call。

和队列关系：审批不是队列任务。审批通过后可以重新投递 queue task。

是否持久化：必须。

跨 worker 一致：必须。

### FailureRecord

用途：结构化记录失败，支持自动重试、去重、防循环、人工交接。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` / `tool_call_id` | 归属 |
| `failure_type` | tool_error、test_failure、approval_rejected、conflict、dirty_worktree、release_gate_fail、timeout、mcp_unavailable |
| `error_signature` | 同类错误去重 |
| `retryable` | 是否可重试 |
| `retry_count` | 已重试次数 |
| `next_action` | retry、fallback、manual、abort |
| `evidence_ref` | 日志、测试结果、截图等 |
| `handoff_note` | 给人工的短说明 |

生命周期：每次失败写入；自动恢复成功后保留为历史；终态失败时成为最终原因之一。

和队列关系：queue task 失败必须转成 FailureRecord，不能只停留在 `error_message`。

是否持久化：必须。

跨 worker 一致：必须。

### MemoryWrite

用途：管理 workflow 对项目记忆的写入，避免“每个 agent 都写一条噪声”。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` | 归属 |
| `memory_type` | decision、gotcha、architecture、tool_feedback、delivery_summary |
| `candidate_text` | 候选内容 |
| `dedupe_key` | 去重键 |
| `noise_score` | 噪声评分 |
| `status` | candidate、approved、written、skipped、merged |
| `target_doc` | 目标记忆文档 |

生命周期：先生成候选；工作流终态时合并摘要；只有高价值内容写入项目记忆。

和队列关系：可由 queue task 生成候选，但写入决策属于 Run 收尾阶段。

是否持久化：建议必须，至少持久化候选和最终写入记录。

跨 worker 一致：必须。

### VerificationResult

用途：每个终态必须带验证结果，解决“做完但没验收”“验收但误解债务”的问题。

关键字段：

| 字段 | 说明 |
|---|---|
| `id` / `run_id` / `step_id` | 归属 |
| `verification_type` | lint、unit_test、probe、playwright、release_gate、sandbox_matrix、manual_review |
| `status` | pass、fail、debt、skipped、not_applicable |
| `command_or_capability` | 验证来源 |
| `evidence_ref` | 输出或 artifact |
| `summary` | 可读摘要 |
| `is_required_for_completion` | 是否阻止 clean completed |
| `created_at` | 时间 |

生命周期：验证步骤产生；Run 终态时汇总为最终裁判。

和队列关系：验证可以通过 queue task 执行，但结果归 WorkflowRun。

是否持久化：必须。

跨 worker 一致：必须。

## 5. 工作流生命周期

建议生命周期：

```text
1. 接收
2. 归类和建账本
3. 边界检查
4. 后台规划
5. 自动执行
6. 暂停确认
7. 恢复执行
8. 验证
9. 产物整理
10. 记忆候选合并
11. 终态裁判
12. 通知用户
```

### 1. 接收

入口可以来自 Agent 对话、scheduler、mailbox、系统事件或模块能力调用。接收后立即创建 `WorkflowRun`，状态为 `waiting`，并写入用户可见摘要。

### 2. 归类和建账本

系统判断任务类型：

1. 只读调研。
2. 代码修改。
3. 文档生成。
4. 测试验证。
5. 发布或提交。
6. 跨模块工具任务。

同时设置初始权限策略、默认验证策略、产物策略。

### 3. 边界检查

后台检查：

1. worktree 是否 dirty。
2. 任务是否涉及模块边界。
3. 是否需要先锁文件或模块。
4. 是否需要用户预确认。
5. 是否存在未完成的冲突 workflow。

dirty worktree 不应该只是日志，它应该进入 `WorkflowRun.dirty_worktree_state`。如果开工前已有 dirty 且任务要改同一区域，Run 应进入 `needs_confirmation` 或 `failed/manual_required`。

### 4. 后台规划

Agent 可生成 Subtask 和 WorkflowStep，但规划结果必须持久化。规划不是终态，不能仅存在模型上下文里。

### 5. 自动执行

只读和低风险动作直接执行。有长耗时或需跨 worker 的动作，通过 `framework_system_task_queues` 投递执行。投递时在参数里带 `workflow_run_id`、`workflow_step_id`、`tool_call_id`、`idempotency_key`。

### 6. 暂停确认

遇到需要确认的动作时：

1. 创建 `ApprovalRequest`。
2. 对应 ToolCall 状态变为 `waiting_approval`。
3. WorkflowRun 状态变为 `needs_confirmation`。
4. 前台只展示确认问题、风险、将发生什么、可选项。
5. 后台保留 resume target。

### 7. 恢复执行

用户批准后，系统校验 payload hash 未变更，然后恢复原 ToolCall 或 Step。不要让 Agent 重新自由生成一个“类似动作”，否则确认绑定失效。

用户拒绝后，根据策略进入 `partial` 或 `failed`，并生成可交接摘要。

### 8. 验证

每个 workflow 的终态都必须有 `VerificationResult`：

1. 文档/调研任务：至少验证产物存在、路径正确、只改允许文件、引用来源足够。
2. 后端改动：默认 `cd backend && pytest` 或相关 `run_test/probe`。
3. 前端改动：lint/typecheck/Playwright 或对应 UI 验证。
4. 模块改动：模块 sandbox 验证和 `git diff --name-only` 边界守卫。
5. 发布任务：release gate。

### 9. 产物整理

临时产物进入 TTL；最终产物链接到 Content IR、framework artifact、桌面发布文件或指定文档。用户只看最终产物和必要证据。

### 10. 记忆候选合并

工作流收尾时只生成一条或少量高价值记忆候选，经过去重、合并、噪声评分后写入。不要每个 Step、每个 Agent、每个工具都写项目记忆。

### 11. 终态裁判

终态必须是明确之一：

| 终态 | 条件 |
|---|---|
| `completed` | 目标完成，必需验证通过，无未解决确认 |
| `partial` | 有有效产物或部分目标完成，但存在债务、未提交、确认拒绝或非阻断失败 |
| `failed` | 目标未达成，自动恢复失败，验证失败或禁止动作 |
| `cancelled` | 用户取消或上游取消 |
| `manual_required` | 系统不能安全继续，需要人工接手 |

`PASS_WITH_DEBT` 不应映射成干净 `completed`。建议映射为 `partial` 或 `completed_with_debt`，前台显示“部分完成”或“完成但有债务”，需要用户明确知道。

### 12. 通知用户

最终通知只包含：

1. 状态。
2. 一句话结果。
3. 产物入口。
4. 如果失败，最短原因和建议下一步。

## 6. 自动执行 / 需要确认 / 禁止自动执行边界

### 自动执行

这些动作默认可自动执行，但仍需记录 ToolCall 或 Step：

| 能力 | 允许范围 |
|---|---|
| 读文件 | 限项目允许扫描边界和授权文件 |
| CodeGraph / codemap | 查询影响面、读取符号、查看调用链 |
| knowledge 检索 | 只读检索 |
| memory 读取 | 只读读取 |
| lint / typecheck | 只读或生成缓存，不改变用户文件 |
| 定向测试 / probe | 访问常驻服务，不重建服务 |
| browser-tools 截图/检查 | 非发布、非外部写入 |
| terminal-tools 安全命令 | cwd 锁定用户工作区，危险命令拦截 |
| 生成草稿 | 写 workspace temp 或 workflow artifact |
| 生成报告到指定文档 | 用户明确指定路径时可执行 |
| 写内部 workflow 状态 | DB/checkpoint/artifact metadata |

### 需要确认

这些动作必须创建 `ApprovalRequest`：

| 动作 | 确认原因 |
|---|---|
| git commit | 用户可能不希望提交当前 dirty 状态 |
| git push / 创建 PR | 外部可见或团队可见副作用 |
| 发布到桌面文件系统 | 从草稿变成用户可见正式文件 |
| 覆盖、移动、删除用户文件 | 可能难恢复 |
| 大量删除或批量重命名 | 高风险 |
| 调用外部发布接口 | 真实外部副作用 |
| 发送 IM / 邮件 / 通知外部人 | 触达真实用户 |
| scheduler 创建/更新/删除 | 未来自动执行副作用 |
| 修改权限、账号、角色 | 安全边界变化 |
| 修改 Agent prompt / 策略 | 影响后续行为 |
| 使用高成本长任务 | 成本和时间风险 |
| release gate 为 PASS_WITH_DEBT 后交付 | 防止误解为干净完成 |

### 禁止自动执行或必须管理员

这些动作不允许普通 workflow 自动执行：

| 动作 | 策略 |
|---|---|
| 清空数据库 | 禁止自动执行，必须管理员且强确认 |
| 生产环境重置 | 禁止自动执行 |
| 真实外部正式发布 | 默认禁止，除非专门发布工作流和管理员确认 |
| 大范围删除用户文件 | 禁止或管理员审批 |
| 读取宿主机真实桌面/任意路径 | 禁止，遵守 desktop-tools / terminal-tools 世界分离 |
| 绕过 capability registry 直接跨模块 import 或读表 | 禁止 |
| 修改 auth / secrets / 密钥 | 管理员审批，且独立安全流程 |
| 关闭安全拦截、提升 shell 权限 | 禁止 |

### 结合现有模块的策略

1. `terminal-tools`：自动执行只限安全命令、工作区 cwd、超时和输出上限内。危险命令转审批或禁止。
2. `browser-tools`：只读浏览和验证可自动；提交表单、发布、购买、删除等外部副作用需确认。
3. `desktop-tools`：读取授权文件可自动；写桌面、发布、删除、覆盖需确认。
4. `github-search`：搜索可自动；创建 issue、PR、评论、push 需确认。
5. `scheduler`：查询可自动；创建、修改、删除定时任务需确认。
6. `agent`：自我规划、checkpoint、内部状态自动；修改系统 prompt、长期策略、默认权限需确认。
7. `knowledge`：检索自动；批量重建、删除知识库、跨用户导入需确认或管理员。
8. `memory`：读取自动；写入走候选和去重，项目级记忆写入应有质量门槛。

## 7. 失败恢复和防循环机制

### 明确终态

每个 workflow 必须结束在明确终态，不能长期停在 running。建议增加后台巡检：

1. `running` 超过心跳阈值：检查 queue task 和 checkpoint。
2. queue task 已 failed：写 FailureRecord，按策略重试或转人工。
3. AgentRun 心跳丢失：标记 interrupted，并从 checkpoint 恢复或转人工。
4. ApprovalRequest 超时：转 failed、partial 或 manual_required。

### 终态必须带验证结果

终态记录至少包含：

1. 最终状态。
2. 必需验证项列表。
3. 每项 VerificationResult。
4. release gate 结果。
5. 产物列表。
6. dirty worktree 结论。
7. 是否有未解决确认。

没有验证结果的“完成”只能是 `partial` 或 `manual_required`，不能是 clean `completed`。

### 自动重试策略

建议三层重试：

| 层级 | 默认次数 | 适用 |
|---|---:|---|
| ToolCall | 2 到 3 次 | 网络抖动、MCP 暂时不可用、只读查询失败 |
| WorkflowStep | 1 到 2 次 | 可重新执行的验证、生成、整理 |
| WorkflowRun | 0 到 1 次 | 整体重新规划，谨慎使用 |

不应重试：

1. 权限拒绝。
2. 用户拒绝审批。
3. 禁止动作。
4. 真实副作用已部分执行且无幂等键。
5. 同一错误签名连续出现并且 diff 没变化。

### 几次后转人工

建议规则：

1. 同一 ToolCall 同一 `error_signature` 连续失败 3 次，转人工。
2. 同一 Step 自动修复 2 轮仍失败，转人工。
3. release gate 连续 2 次失败且失败项不变，转人工。
4. dirty worktree 冲突无法自动归因，立即转确认或人工。
5. 审批超时后不继续执行有风险动作。

### 避免 Agent 自己一直循环修

机制：

1. 保存每轮失败签名和变更摘要。
2. 如果错误签名相同、修改文件相同、验证输出相同，判定为 stuck。
3. 限制同一 Run 的自修轮数，例如最多 2 轮。
4. 每轮自修必须声明“这次修复改变了什么假设”。
5. 没有新证据时不允许继续自修。
6. 进入 `manual_required` 时给出最小交接说明，而不是继续尝试。

现有 Agent stuck detector 可作为基础，但需要把结果写入 WorkflowRun / FailureRecord，而不是只影响当前对话。

### 防止多个 Agent 修改同一文件冲突

建议引入 workflow 级文件锁策略，借鉴现有 codemap `locks.json` 的持久化文件锁思路：

1. 修改前声明 write set，至少到文件粒度。
2. 对目标文件或目录获取持久锁，包含 run id、step id、owner、TTL。
3. 锁超时必须续租，不能无限占用。
4. 同一文件已有锁时，新 workflow 等待、转人工或只读分析。
5. 写入前检查文件 hash 是否仍等于读入时 hash。
6. 写入后记录 changed files。

### dirty worktree 纳入任务状态

建议每个代码类 workflow 记录三次 dirty：

1. 开工前：区分用户已有改动和 clean。
2. 写入前：确认目标文件没有外部变化。
3. 收尾前：判断哪些改动属于本 Run。

状态策略：

| 情况 | 结果 |
|---|---|
| 开工 clean，收尾只有本 Run 改动 | 可 completed |
| 开工 dirty，但用户明确允许在 dirty 上工作 | 可 partial 或 completed，需记录 |
| 出现外部 dirty 干扰 | needs_confirmation 或 manual_required |
| 做完但未提交且任务要求提交 | partial / needs_confirmation |

### release gate 纳入最终裁判

release gate 结果必须写入 `VerificationResult`，并影响 Run 终态：

| release gate | Run 终态建议 |
|---|---|
| PASS | completed |
| PASS_WITH_DEBT | partial 或 completed_with_debt |
| FAIL | failed 或 manual_required |
| 未运行但任务要求 | partial |
| 不适用 | skipped，并说明原因 |

不要把 `release_safe=true` 简化成“完成”。必须同时展示 `has_debt`。

## 8. 产物管理和项目记忆降噪

### 产物分类

| 类型 | 示例 | 生命周期 |
|---|---|---|
| 临时产物 | 原始日志、临时 JSON、中间截图、工具 stdout、草稿 patch | TTL 自动清理 |
| 候选产物 | 报告草稿、测试结果摘要、截图精选、文档草稿 | Run 结束时选择保留或发布 |
| 正式产物 | 用户指定报告、生成文档、表格、最终截图、发布文件 | 写入 Content IR / Resource / framework artifact / 桌面文件 |
| 管理员产物 | stack trace、完整 MCP log、脱敏 tool args、队列调度细节 | 仅管理员可见，按审计周期保留 |
| 记忆产物 | 决策、架构结论、踩坑、工具反馈 | 去重合并后写项目记忆 |

### 哪些是临时产物

1. 每次 tool call 原始输出。
2. 中间文件、缓存、临时表格。
3. 自动重试过程中的失败日志。
4. 未选中的截图和浏览器 trace。
5. Agent 内部计划草稿。

这些应有 TTL、大小上限和 workflow 归属。Run 完成后只保留摘要和必要证据。

### 哪些要发布到桌面文件系统

只有用户明确要求或点击确认后才发布：

1. 最终报告。
2. 交付文档。
3. 生成表格。
4. 用户要下载或打开的图片、截图、压缩包。
5. 明确从 workspace 草稿 publish 的成果。

发布前应确认目标路径、覆盖行为和文件名。

### 哪些只给管理员看

1. 完整 tool arguments。
2. MCP 原始失败堆栈。
3. 模型输入输出的敏感片段。
4. 队列 worker 和锁信息。
5. 脱敏前路径或用户数据。
6. 安全策略命中记录。

### 哪些要写入项目记忆

只写高价值、可复用的信息：

1. 架构决策。
2. 项目规则的新解释或冲突解决。
3. 反复踩坑的修复方法。
4. 重要工具行为反馈。
5. 已验证的模块边界和能力契约。

不要写：

1. “某任务已完成”这种一次性流水账，除非是关键里程碑。
2. 每次测试命令输出。
3. 临时失败又自动恢复的噪声。
4. Agent 自我描述。
5. 未验证猜测。

### 如何自动清理

建议：

1. 临时 artifact 默认 7 到 14 天 TTL。
2. 大日志默认只保留摘要和压缩引用。
3. failed run 保留更长，但仍按审计周期归档。
4. 被发布的正式产物不自动删除。
5. MemoryWrite 候选若未采纳，随 Run 归档。

### 防止项目记忆越来越吵

建立记忆质量门槛：

1. 每个 WorkflowRun 最多自动写 1 条总结性记忆。
2. 同主题必须更新或合并旧记忆，不新建重复文档。
3. MemoryWrite 必须有 `memory_type`、`dedupe_key`、`evidence_ref`。
4. 低价值候选标记 `skipped`，不写入。
5. release / architecture / tool feedback 分不同目标文档。
6. 定期做 memory compaction：把连续流水账合并成“当前有效规则”。

## 9. 和现有模块的集成方案

### 核心依赖

| 组件 | 角色 |
|---|---|
| `modules/agent` | 工作流中枢所有者，负责 WorkflowRun、AgentRun、审批、恢复、终态裁判 |
| `framework_system_task_queues` | 后台执行队列，负责排队、worker 消费、基础重试 |
| capability registry / `/api/modules/call` | 跨模块调用唯一通路 |
| notification service | 用户状态通知 |
| Content IR / Resource / framework artifact | 正式产物存储和发布链路 |
| codemap / CodeGraph | 影响面分析、文件锁启发、代码理解 |
| release gate / dev toolkit | 收尾验证和最终裁判证据 |

### 工具节点

| 模块 | 作为工作流节点的职责 |
|---|---|
| `memory` | 读取历史、写入高价值记忆候选 |
| `knowledge` | 检索资料和上下文 |
| `terminal-tools` | 执行受限命令、测试、lint |
| `browser-tools` | UI 验证、截图、网页检查 |
| `desktop-tools` | 桌面文件读取、发布、用户文件操作 |
| `scheduler` | 定时触发 workflow 或等待回调 |
| `docs-open` | 文档读取、预览 |
| `office-gen` | 生成文档、报告 |
| `excel-engine` | 表格生成和处理 |

这些模块不应该直接互相 import。Agent 工作流中枢也不应该直接读别的模块业务表。所有业务能力调用都走统一 capability 路径，后端以 `register_capability` 为准，manifest 的 public actions 只作为声明元数据。

### workflow run 状态放哪里

建议第一阶段放在 `modules/agent`。

理由：

1. 这个中枢的第一用户是 Agent 后台任务，不是所有模块的通用编排。
2. 放在框架会让 `backend/app` 快速膨胀，违反“框架接口不随模块膨胀”。
3. Agent 已有 approval、checkpoint、events、tool loop、stuck detector 等基础。
4. 以模块能力暴露，可以保持跨模块统一通路。

如何避免框架被 Agent 绑架：

1. Agent 只调用框架公共能力，不修改框架内部行为。
2. 工作流状态通过 `agent` capability 暴露，不要求其他模块 import Agent 代码。
3. 框架任务队列只知道 `task_type`、`parameters`、`status`，不理解 Agent 业务语义。
4. 未来如多个模块都需要通用 workflow，再把抽象沉淀成框架任务，而不是一开始上移。

如果放 `backend/app`，如何避免框架膨胀：

1. 只能放极薄的通用对象，例如 `correlation_id`、`idempotency_key`、通用 artifact link。
2. 不放 Agent 专属状态、prompt、subtask、tool trace。
3. 不把 agent workflow API 做成框架 API。

### 是否应该建新表

应该。最小 Phase 1 建议：

1. `agent_workflow_runs`
2. `agent_workflow_steps`
3. `agent_tool_calls`
4. `agent_workflow_artifacts`
5. `agent_verification_results`
6. 复用或扩展现有 `agent_approval_queue`
7. 复用现有 `agent_checkpoints`，增加 workflow 归属

### 是否复用 framework_system_task_queues

复用，但只作为执行载体。建议第一阶段不改框架表结构，先在 `parameters` 中写：

```json
{
  "workflow_run_id": "...",
  "workflow_step_id": "...",
  "tool_call_id": "...",
  "idempotency_key": "..."
}
```

后续如果确实需要通用能力，再作为独立框架任务增加：

1. `correlation_id`
2. `idempotency_key`
3. `owner_kind`
4. `heartbeat_at`

这些必须保持通用，不带 Agent 语义。

## 10. 开源项目对比

本次优先参考了本地资料：

1. `/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms`
2. `/Users/hekunhua/Documents/Agent/reference_sources/10_agent_platform_reference/2026_06_25_core_agent_frameworks`

未额外下载参考项目。

### Dify

项目名：Dify。

它怎么表达 workflow / task / agent / tool：

Dify 用 workflow graph/canvas 表达流程，用 `WorkflowRun` 表达一次运行，用 `WorkflowNodeExecution` 表达节点执行。Agent 可使用 Function Calling、ReAct、内置工具和自定义工具。参考路径：

```text
reference_sources/10_agent_platform_reference/2026_06_25_agent_platforms/dify/api/models/workflow.py
```

它怎么做状态持久化：

Run、node execution、pause 都是数据库模型。`WorkflowRun` 保存 graph、inputs、outputs、status、error、elapsed_time、token usage 等；节点执行单独记录；大对象可 offload。

它怎么做失败恢复：

通过 run/node 状态、error 字段和 pause state 保存运行时状态。失败不是只靠日志，而是进入模型对象。

它怎么做人类确认：

有 `WorkflowPause` 和 human input policy，把暂停原因、表单 token、resume context 作为独立对象。

它怎么管理产物：

偏应用运行和节点输出管理，大对象有 offload 机制。

对我们项目可借鉴的点：

1. `WorkflowRun` 和 `WorkflowNodeExecution` 分离。
2. Pause 独立建模，而不是把审批塞进错误。
3. human input 按 surface 和 policy 控制。
4. 大对象不要塞主表。

不适合照搬的点：

1. 不需要先做完整可视化 workflow builder。
2. 不需要 app marketplace 和复杂应用发布模型。
3. V2 的重点是无感后台推进，不是让用户编排节点。

### LangGraph

项目名：LangGraph。

它怎么表达 workflow / task / agent / tool：

LangGraph 用 graph 表达状态机，thread/run/checkpoint 表达长期运行。节点可以是 Agent 或工具，状态在 superstep 之间推进。

它怎么做状态持久化：

通过 checkpointer 持久化状态，支持 Postgres checkpoint saver。checkpoint 保存 thread 状态、任务状态、pending writes。

它怎么做失败恢复：

关键点是 pending writes：节点成功产生的写入可以被记录，失败恢复时避免盲目重跑已经成功的部分。

它怎么做人类确认：

通过 interrupt / resume 模式暂停运行，等待外部输入后继续。

它怎么管理产物：

LangGraph 不是产物系统，更多关注状态和恢复。

对我们项目可借鉴的点：

1. checkpoint 是长期 Agent 的核心，不是附属日志。
2. pending writes 能防止副作用重复执行。
3. interrupt / resume 模式适合审批。
4. thread/run/checkpoint 概念适合 V2 AgentRun。

不适合照搬的点：

1. 不要直接照搬其序列化机制，V2 应存受控 JSON schema。
2. 不需要把所有任务都变成复杂 graph DSL。

### OpenHands

项目名：OpenHands / OpenDevin。

它怎么表达 workflow / task / agent / tool：

OpenHands 把 conversation、agent server、automation server、runtime backend 分层。Agent 在 conversation 中执行工具，自动化入口可由 scheduler 或 webhook 触发。

它怎么做状态持久化：

有本地文件、SQL conversation、event storage 等可选存储，trajectory 可下载。

它怎么做失败恢复：

主要通过 conversation lifecycle、event storage、runtime 边界恢复。它的重点是交互式软件工程 Agent，而不是强事务 workflow。

它怎么做人类确认：

更偏控制台和 runtime 安全边界，确认模型不是最值得照搬的部分。

它怎么管理产物：

通过 workspace、trajectory、conversation artifacts 管理。

对我们项目可借鉴的点：

1. Agent Server 和 Automation Server 分层。
2. conversation trajectory 作为审计和复盘材料。
3. 自动化入口不等于用户 UI。

不适合照搬的点：

1. 不要重新引入 Docker / VM / 多后端隔离争论，V2 已明确 terminal-tools 本地执行边界。
2. 不需要复制云平台和多 runtime 后端。

### opencode

项目名：opencode。

它怎么表达 workflow / task / agent / tool：

opencode 区分 plan/build/general agent，工具有明确的 `Tool.Context`，包含 session、agent、assistant message、tool call id。

它怎么做状态持久化：

强调 durable text/tool lifecycle，工具调用有归属和上下文快照。

它怎么做失败恢复：

进程丢失时，把 running tool 结算为 interrupted，而不是假装继续或盲目重放。

它怎么做人类确认：

通过 plan/build 权限差异和 pending question/reply/reject 等机制表达确认。

它怎么管理产物：

对 patch/edit 语义比较诚实，承认 apply_patch 是顺序副作用，不假装事务回滚。

对我们项目可借鉴的点：

1. ToolCall 必须有 durable context。
2. 工具调用要能被结算为 interrupted。
3. plan/read-only 和 build/write 权限分离。
4. 不重复执行可能有副作用的工具。

不适合照搬的点：

1. 不需要复制其 TypeScript / Effect 技术栈。
2. V2 已有模块能力和 Python 后端结构，应吸收语义而非技术栈。

### OpenClaw

项目名：OpenClaw。

它怎么表达 workflow / task / agent / tool：

OpenClaw 是 local-first gateway，围绕 sessions、channels、tools、events 组织 Agent runtime，有后台 lanes 和 session locks。

它怎么做状态持久化：

本地状态目录保存 sessions、auth、credentials、workspace。并强调 session locks 和并发上限。

它怎么做失败恢复：

通过 session lock、后台 lane contract、全局并发上限减少冲突，失败可归属到 session。

它怎么做人类确认：

有 DM pairing、allowlist、exec approval 等确认策略。

它怎么管理产物：

通过 workspace、skills、prompt files 等本地资源管理。

对我们项目可借鉴的点：

1. session lock 和 lane contract 很适合多 agent 防冲突。
2. local-first gateway 的控制面思路适合 V2 桌面壳。
3. 工具面最小化，减少 Agent 自由度。

不适合照搬的点：

1. 不需要多社交渠道网关。
2. 不要默认 host full-access 工具。

### Hermes

项目名：Hermes Agent。

它怎么表达 workflow / task / agent / tool：

Hermes 偏长期自改进 Agent，用 conversation、skills、cron、subagent、RPC tools 表达任务。

它怎么做状态持久化：

长期状态包括 memory、skills、session search、user model。cron 通过外部 one-shot callback 模式触发。

它怎么做失败恢复：

支持 interrupt、redirect、retry、undo 等交互语义。

它怎么做人类确认：

有 command approval、allowlist、危险命令审批。

它怎么管理产物：

skills、memories、trajectory、workspace instructions 都是长期产物。

对我们项目可借鉴的点：

1. 外部 scheduler 只负责触发 callback，Agent 中枢负责业务推进。
2. 危险命令 blocklist 和审批上下文隔离。
3. 长期记忆需要治理，不能无限写。

不适合照搬的点：

1. 不需要多聊天平台网关。
2. 不需要多 terminal backend。

### Coze Studio

项目名：Coze Studio。

它怎么表达 workflow / task / agent / tool：

Coze 用 IDL 定义 workflow、node type、run mode、run history、resume、cancel、debug 等 API。

它怎么做状态持久化：

通过执行 ID、run history、node process、error code/message 表达状态。

它怎么做失败恢复：

有 resume、cancel、debug URL 等稳定接口，强调产品 API contract。

它怎么做人类确认：

更多体现在 resume/test/debug 合同，不是一个单独审批系统。

它怎么管理产物：

偏发布、模板、插件、市场体系。

对我们项目可借鉴的点：

1. API contract 要稳定，不要让前台依赖内部工具细节。
2. run history 和 node process 查询适合管理员视角。

不适合照搬的点：

1. 不需要市场、模板、多人协作重产品壳。
2. 不需要先做复杂可视化节点编辑器。

### Letta

项目名：Letta。

它怎么表达 workflow / task / agent / tool：

Letta 更偏 stateful agent API，核心是 agent、memory blocks、tools、messages。

它怎么做状态持久化：

长期 agent state、conversation、memory block 是重点。

它怎么做失败恢复：

有 client tool pause 和 checkpoint start/finish 的方向，但不是完整 workflow 中枢模型。

它怎么做人类确认：

client tools 可暂停等待客户端返回。

它怎么管理产物：

产物更偏 agent memory 和 message state。

对我们项目可借鉴的点：

1. Memory block 思路适合长期 Agent 上下文治理。
2. stateful agent API 对 V2 Agent 模块有参考价值。

不适合照搬的点：

1. 它不是后端 workflow center 的主参考。
2. 不应把记忆系统等同于工作流账本。

## 11. 推荐落地路线

### Phase 1：最小后端工作流中枢

目标：建立一个能真实承载用户任务状态的最小 ledger。

范围：

1. 在 `modules/agent` 新建 workflow run / step / tool call / artifact / verification 相关表。
2. 复用现有 `agent_approval_queue` 和 `agent_checkpoints`，补 workflow 关联。
3. Agent 接收任务时创建 WorkflowRun。
4. 后台执行时把 `workflow_run_id` 写入 `framework_system_task_queues.parameters`。
5. 前台只读 Run 的极简状态。
6. 终态必须写 VerificationResult。
7. 收尾跑 `git diff --name-only` 边界检查，代码类任务纳入 dirty 状态。

第一阶段不做：

1. 可视化编排器。
2. 多 agent 高级调度。
3. 通用框架 workflow 平台。
4. 自动 push / publish。
5. 复杂记忆自动生成。

最小验收：

1. 一个用户任务能从 waiting 到 completed/failed/partial。
2. 后台 queue task 失败能反映到 WorkflowRun。
3. 需要确认时 Run 进入 needs_confirmation。
4. 最终状态一定带验证结果。
5. 前台不需要知道 MCP/tool 细节。

### Phase 2：后台自动推进和恢复

目标：让中枢具备可靠恢复能力。

范围：

1. ToolCall 幂等键。
2. running tool interrupted settlement。
3. Step / Tool / Run 分层重试。
4. FailureRecord 和 error_signature。
5. checkpoint resume。
6. 审批通过后的原 tool call 恢复。
7. 文件锁和 dirty worktree 冲突检测。

验收：

1. worker 重启后 Run 不丢状态。
2. MCP 暂时失败可自动重试。
3. 同一错误不会无限循环修。
4. 有副作用工具不会盲目重复执行。

### Phase 3：前台极简状态和通知

目标：让用户只感知任务状态和必要确认。

范围：

1. 前台 6 状态模型。
2. 通知策略。
3. 默认折叠的工作时间线。
4. 需要确认卡片。
5. 管理员详情入口。

验收：

1. 普通用户不看到 agent/MCP/queue 细节。
2. 失败时能看到简短原因和下一步。
3. 确认请求能明确展示风险和结果。

### Phase 4：产物/记忆治理

目标：减少产物和项目记忆噪声。

范围：

1. Artifact 生命周期：temp、candidate、published、archived。
2. 临时产物 TTL 清理。
3. MemoryWrite 候选、去重、噪声评分。
4. 每个 Run 一条总结性记忆上限。
5. 产物发布确认。

验收：

1. 临时日志不会无限增长。
2. 用户只看到最终产物。
3. 项目记忆不被流水账污染。

### Phase 5：高级多 agent 编排

目标：在中枢稳定后再增强协作能力。

范围：

1. Subtask tree。
2. 多 agent lane。
3. 文件锁调度。
4. agent 专长分派。
5. 跨 workflow 资源调度。

验收：

1. 多 agent 不同时修改同一文件。
2. 子任务失败能汇总到 Run。
3. 管理员能看完整运行图。

## 12. 不建议现在做的事

1. 不建议把核心状态直接放进 `backend/app` 做通用 workflow 平台。
2. 不建议把 `framework_system_task_queues` 改造成万能工作流表。
3. 不建议先做复杂可视化节点编辑器。
4. 不建议让用户看到完整 MCP/tool/agent 流程。
5. 不建议自动提交、自动 push、自动发布。
6. 不建议绕过 capability registry 做模块直接 import。
7. 不建议把所有中间日志都写入项目记忆。
8. 不建议重新讨论 Docker 强隔离，当前 terminal-tools 安全边界已经是项目明确取舍。
9. 不建议把 `PASS_WITH_DEBT` 当 clean completed。
10. 不建议在没有幂等键和 checkpoint 的情况下自动重放副作用工具。

## 13. 下一封实现任务建议

建议下一封任务聚焦 Phase 1，范围要小：

```text
实现 modules/agent 的最小 WorkflowRun 后端账本。

要求：
1. 只改 modules/agent，除非明确作为框架任务另开。
2. 新增 agent_workflow_runs、agent_workflow_steps、agent_tool_calls、agent_workflow_artifacts、agent_verification_results 的最小模型和迁移。
3. WorkflowRun 状态只支持 waiting、processing、needs_confirmation、completed、failed、partial、cancelled。
4. 将现有 Agent 后台长任务和 framework_system_task_queues 通过 workflow_run_id 关联。
5. 复用 agent_approval_queue，补 run/step/tool 关联和 resume target。
6. 提供 capability/API：create_workflow、get_workflow_status、list_workflow_artifacts、record_verification。
7. 前台只展示极简状态，不展示工具细节。
8. 完成后跑模块 sandbox、相关 backend tests、git diff --name-only 边界检查。
9. 不做可视化编排器，不做多 agent lane，不做自动 push/publish。
```

第一阶段成功的标志不是“功能多”，而是任何后台 Agent 任务都能回答四个问题：

1. 现在是什么状态？
2. 卡在哪里，是否需要确认？
3. 最终产物在哪里？
4. 为什么可以算完成，或者为什么不能算完成？
