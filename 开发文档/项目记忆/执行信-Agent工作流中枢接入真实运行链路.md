# 执行信：Agent 工作流中枢接入真实运行链路

收件人：Codex / 新会话执行代理
任务类型：业务模块 / Agent 中枢二阶段落地
建议 agent 标识：`codex-agent-workflow-runtime-link`
优先级：高
边界：**只改 `modules/agent/`，除项目记忆/交付报告外不得修改 `backend/app/`、`frontend/src/` 或其他模块**

---

## 0. 任务一句话

第一阶段已经在 `modules/agent/` 内落地了 Agent 专属 workflow 账本、状态机、API、capability、前端状态和测试。

本任务要做第二阶段：

> 把 workflow 中枢真正接入 Agent 的实际对话、工具调用、审批、子 Agent、验证与产物链路，让用户发起真实任务时，后端自动生成和推进 workflow，而不是只停留在可手动调用的账本能力。

---

## 1. 必读材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/03_模块开发文档/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/agent/README.md`
5. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/后端无感-agent-工作流中枢落地.md`
6. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-后端无感Agent工作流中枢完整落地.md`

请重点阅读第一阶段新增文件：

```text
modules/agent/backend/workflow_models.py
modules/agent/backend/services/workflow_service.py
modules/agent/backend/handlers/workflow.py
modules/agent/backend/tests/test_workflow_service.py
modules/agent/backend/tests/test_workflow_api.py
modules/agent/frontend/components/WorkflowList.vue
modules/agent/frontend/components/WorkflowDetail.vue
modules/agent/frontend/components/WorkflowStatusBadge.vue
modules/agent/frontend/components/workflowTypes.ts
```

---

## 2. 当前基线说明

第一阶段已完成：

- `agent_workflow_runs`
- `agent_workflow_steps`
- `agent_tool_calls`
- `agent_workflow_artifacts`
- `agent_verification_results`
- `agent_failure_records`
- `agent_approval_queue` workflow 字段扩展
- `agent_checkpoints` workflow 字段扩展
- workflow capability / HTTP API
- 前端极简状态
- sandbox/backend tests

本会话验收时发现并修复了一个小问题：

- workflow capability runtime 注册参数为空，导致 `capability_contract_diff(agent)` 参数漂移；已补齐 runtime parameters 后复验通过。

已复验：

```text
lint modules/agent/backend/handlers/workflow.py -> pass
capability_contract_diff(module="agent") -> 0 drift
run_test modules/agent/backend/tests/test_workflow_api.py -> 6 passed
```

---

## 3. 本任务目标

第一阶段是“账本可用”。

第二阶段要做到“真实运行自动落账”。

目标状态：

1. 用户正常和 Agent 对话时，系统自动创建或关联 workflow run。
2. Agent 实际执行工具调用时，自动记录 `agent_tool_calls`。
3. Agent 实际进入审批时，自动关联 `workflow_run_id / workflow_step_id / tool_call_id / payload_hash / resume_target`。
4. 工具执行结果、失败、重试、降级能自动进入 step / verification / failure records。
5. 子 Agent 派发、返回、失败能作为 workflow step 或 artifact 被追踪。
6. 关键产物能写入 workflow artifacts，并在前端详情中看到摘要。
7. 用户前端仍只看 6 类极简状态；管理员可展开技术细节。

---

## 4. 严格边界

### 4.1 允许修改

```text
modules/agent/
开发文档/项目记忆/   # 仅交付报告、memory、反馈
```

### 4.2 禁止修改

```text
backend/app/
frontend/src/
modules/knowledge/
modules/memory/
modules/codemap/
modules/terminal-tools/
modules/desktop-tools/
其他 modules/*
```

### 4.3 跨模块规则

如果需要调用 knowledge/memory/codemap/terminal-tools/desktop-tools，只能通过：

- 后端 capability registry / `/api/modules/call`
- 前端 runtime SDK

禁止直接 import 其他模块代码，禁止直接读写其他模块表。

---

## 5. 重点接入点

请先用 `code_explore` 查准，不要猜文件。

重点看：

```text
modules/agent/backend/router.py
modules/agent/backend/runtime/tool_loop_runtime.py
modules/agent/backend/runtime/understanding_loop.py
modules/agent/backend/services/action_policy.py
modules/agent/backend/services/review_service.py
modules/agent/backend/engine/workflow_strategy.py
modules/agent/backend/engine/context_snapshot.py
modules/agent/backend/engine/failure_diagnostics.py
modules/agent/backend/handlers/workflow.py
modules/agent/backend/services/workflow_service.py
modules/agent/frontend/index.vue
modules/agent/frontend/components/ConversationSidebar.vue
modules/agent/frontend/components/WorkflowDetail.vue
```

实际文件以当前代码为准。

---

## 6. 具体需求

### 6.1 对话自动创建 / 关联 workflow

当用户发起一个可视为“任务”的 Agent 请求时：

- 自动创建 `agent_workflow_runs`，或关联已有 run。
- `conversation_id` / `message_id` / `session_id` 能和 workflow run 互查。
- 简单闲聊可以不创建 workflow，但要有明确判断规则。

建议规则：

- 涉及工具调用、文件操作、生成产物、长任务、审批、子 Agent 的请求，必须有 workflow。
- 纯问答/闲聊可不创建。

### 6.2 工具调用自动落账

Agent 真正调用工具时，自动记录：

- run_id
- step_id
- tool_name
- target_module/action
- sanitized arguments summary
- arguments_hash
- side_effect_level
- approval_policy
- idempotency_key
- status
- result_ref / error_signature

注意：

- 不要把敏感参数完整明文塞进普通用户可见摘要。
- 有副作用的工具必须有 idempotency_key。
- 失败工具必须进入 failure records 或 verification debt/fail。

### 6.3 审批恢复接入 workflow

现有审批能力要和真实运行链路打通：

- 请求审批时，必须带 workflow_run_id / workflow_step_id / tool_call_id。
- payload_hash 必须基于待执行动作，不允许用户确认后动作漂移。
- 用户批准后恢复原 tool call，不重新自由生成一个新动作。
- 用户拒绝后 workflow 进入 failed 或 partial，不能当 completed。

### 6.4 checkpoint 接入 workflow

checkpoint 不能只按 conversation 粗粒度存。

要求：

- checkpoint 记录 workflow_run_id / workflow_step_id / agent_run_id。
- 恢复时能知道回到哪个 run、哪个 step、哪个 tool_call。
- 多 worker 下不依赖进程内内存。

### 6.5 验证裁判接入真实结束条件

真实任务结束时，不允许无验证直接 completed。

建议：

- 如果产生代码/文件/配置改动，必须记录 lint/test/probe/sandbox/release_gate 等 verification。
- 如果只是问答，可记录轻量 verification：`answer_review` / `no_side_effect`。
- 有债务必须 partial。
- 失败必须 failed。

### 6.6 子 Agent 接入 workflow

如果 Agent 支持 `spawn_subagent`：

- 每个子 Agent 派发记为 step。
- 子 Agent 输出记为 artifact 或 step output。
- 子 Agent 失败记入 failure records。
- 主 Agent 合并结果时记录 verification。

### 6.7 前端极简展示保持克制

不要把前端做成复杂项目管理器。

用户看到：

- 当前任务状态
- 当前进度摘要
- 是否需要确认
- 主要产物
- 最近更新时间

管理员展开后看到：

- steps
- tool calls
- verifications
- failures
- queue task ids
- developer summary

---

## 7. 验收要求

### 7.1 必须新增/补齐测试

建议新增：

```text
modules/agent/backend/tests/test_workflow_runtime_link.py
```

至少覆盖：

1. 工具调用时自动生成 tool_call ledger。
2. 有副作用工具自动生成 idempotency_key。
3. 审批请求关联 run/step/tool_call/payload_hash/resume_target。
4. 审批通过后恢复原 tool_call。
5. 审批拒绝后 workflow 不会 completed。
6. 无 verification 不允许真实任务 clean completed。
7. PASS_WITH_DEBT 或 debt verification 映射为 partial。
8. 子 Agent step 能记录并合并结果。

如已有测试文件更合适，可补在现有测试中，但名称要清楚。

### 7.2 必跑验证

优先使用 MCP：

```text
plan_task(module_key="agent")
worktree_guard(module_key="agent")
code_explore(...)
lint(path="modules/agent/...")
run_test(target="modules/agent/backend/tests/test_workflow_service.py")
run_test(target="modules/agent/backend/tests/test_workflow_api.py")
run_test(target="modules/agent/backend/tests/test_workflow_runtime_link.py")
run_test(target="modules/agent/sandbox/test_module.py")
capability_contract_diff(module="agent", include_parameters=true)
call_capability(module="agent", action="create_workflow", ...)
call_capability(module="agent", action="record_tool_call", ...)
call_capability(module="agent", action="finalize_workflow", ...)
finish_task(module_key="agent")
memory_write(agent="codex-agent-workflow-runtime-link")
mcp_feedback(agent="codex-agent-workflow-runtime-link")
```

如果 MCP 临时不可用，用等价命令，但报告要说明。

### 7.3 活系统验证

至少用真实 capability 验：

1. 创建 workflow。
2. 记录 step。
3. 记录 tool_call。
4. 请求 approval。
5. 记录 verification。
6. finalize 到 completed / partial / failed 三类至少覆盖两类。
7. 清理本次探针数据，或用明确测试标记方便后续清理。

---

## 8. 验收红线

以下情况判不通过：

1. 修改 `backend/app/`、`frontend/src/` 或其他模块。
2. workflow 只停留在手动 API，真实 Agent 运行没有自动落账。
3. 工具调用未记录 arguments_hash。
4. 有副作用工具没有 idempotency_key。
5. 审批批准后重新生成动作，而不是恢复原 tool_call。
6. 无 verification 也能 clean completed。
7. 有债务显示为 completed。
8. 前端使用 `any` / `as any` / `@ts-ignore` 绕过类型。
9. 测试失败但交付报告写成功。

---

## 9. 交付物

请交付：

1. 修改文件清单。
2. 真实运行链路接入点说明。
3. 对话/工具/审批/checkpoint/子 Agent 如何关联 workflow 的说明。
4. 新增或补齐测试清单。
5. capability 和 HTTP API 验证结果。
6. 边界检查结果。
7. 剩余风险。
8. 项目记忆：`memory_write(agent="codex-agent-workflow-runtime-link")`。
9. MCP 反馈：`mcp_feedback(agent="codex-agent-workflow-runtime-link")`。

---

## 10. 一句话目标

第一阶段让 Agent 有了 workflow 账本；本阶段要让真实 Agent 工作自动进入账本，做到用户无感、后端可恢复、管理员可审计。
