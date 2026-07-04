# 执行信：后端无感 Agent 工作流中枢完整落地

收件人：Codex / 新会话执行代理
任务类型：业务模块 / Agent 中枢落地
建议 agent 标识：`codex-agent-workflow-ledger`
优先级：高
边界：**只改 `modules/agent/`，除文档记忆外不得修改框架 `backend/app/`、`frontend/src/` 或其他模块**

---

## 0. 先读材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/03_模块开发文档/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/agent/README.md`
5. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/后端无感Agent工作流中枢调研报告.md`

如果发现当前工作区已有别人正在改 `modules/agent/`，不要覆盖，先用 `git status --short` 和实际 diff 判断基线，把别人已有改动当作前置状态接着做。

---

## 1. 背景和总目标

用户明确希望：

> 更多内容在后端运行，用户无感知；前端只呈现少数稳定状态，不把复杂过程暴露给用户。

本任务要把 Agent 从“对话 + 工具调用”升级为“后端可恢复、可审计、可暂停、可继续的工作流中枢”。

核心取舍：

- 前端轻：只显示 6 个用户能懂的状态。
- 后端重：计划、步骤、工具调用、审批、checkpoint、恢复、债务都落在后端。
- 模块内闭环：本次只在 `modules/agent/` 内建设，不扩展框架 `framework_workflow_*`。
- 框架任务队列只当执行队列，不当业务账本。

---

## 2. 必守边界

### 2.1 允许修改

```text
modules/agent/
开发文档/项目记忆/   # 只允许写本次任务记忆/反馈/交付说明
```

### 2.2 禁止修改

```text
backend/app/
frontend/src/
modules/knowledge/
modules/memory/
modules/codemap/
其他 modules/*
```

### 2.3 跨模块规则

Agent 如果需要知识库、记忆、代码地图等能力，只能通过框架统一通路调用：

- 后端：`/api/modules/call` / capability registry / 已注册能力
- 前端 runtime：`platform.modules.call` / `platform.modules.capabilities`

禁止：

- 直接 import 其他模块代码
- 直接读写其他模块业务表
- 私自绕开能力注册表

---

## 3. 不要扩展的旧系统

仓库里已有框架级 workflow 骨架：

- `backend/app/models/platform_workflow.py`
- `backend/app/routers/workflow.py`
- 相关 `framework_workflow_*` 表

这套是平台骨架，当前不要把 Agent 业务塞进去，也不要为了 Agent 改它。

本任务的新账本应在 Agent 模块内，例如：

```text
agent_workflow_runs
agent_workflow_steps
agent_workflow_tool_calls
agent_workflow_events
agent_workflow_artifacts
agent_workflow_debts
```

实际表名可按当前代码风格调整，但必须以 `agent_` 前缀归属 Agent 模块。

---

## 4. 用户可见状态：只保留 6 个

前端和 API 对外只暴露以下 6 个状态：

| 状态 | 含义 |
|---|---|
| `queued` / 等待中 | 已接收任务，等待后端调度 |
| `running` / 处理中 | 后端正在执行 |
| `needs_approval` / 需要确认 | 等用户确认敏感步骤或分支选择 |
| `completed` / 已完成 | 干净完成，无阻断债务 |
| `failed` / 失败 | 无法继续或关键步骤失败 |
| `partial` / 部分完成 | 有产出，但有明确债务或部分失败 |

注意：

- `PASS_WITH_DEBT` 不等于干净完成。
- 内部可以有更细状态，但前端展示必须映射到这 6 类。
- 用户不应看到技术型状态爆炸，例如 raw pending/running/succeeded/failed/retry/checkpoint/resume 等一长串。

---

## 5. 后端设计要求

### 5.1 WorkflowRun

每个用户任务创建一个 WorkflowRun，至少记录：

- `id`
- `conversation_id`
- `user_id`
- `title`
- `goal`
- `visible_status`
- `internal_status`
- `progress_percent`
- `current_step_id`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`
- `last_error`
- `debt_count`
- `metadata` / `extra_meta`

### 5.2 WorkflowStep

每个 run 有多个 step，至少记录：

- `id`
- `workflow_run_id`
- `parent_step_id`
- `step_type`
- `title`
- `visible_status`
- `internal_status`
- `order_index`
- `input_summary`
- `output_summary`
- `error_message`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

### 5.3 ToolCall Ledger

工具调用必须落账，至少记录：

- `id`
- `workflow_run_id`
- `workflow_step_id`
- `tool_name`
- `tool_args_summary`
- `tool_args_hash`
- `status`
- `started_at`
- `finished_at`
- `result_summary`
- `error_message`
- `requires_approval`
- `approval_id`

敏感内容不要完整明文塞入 summary；必要时存 hash + 摘要。

### 5.4 Event Timeline

需要有 timeline/event 账本，用于前端“已工作”展示和审计恢复：

- run created
- step started
- tool requested
- tool approved / rejected
- checkpoint saved
- step completed
- debt recorded
- run completed / failed / partial

### 5.5 Debt Ledger

对“部分完成”和历史债务要结构化记录：

- `workflow_run_id`
- `workflow_step_id`
- `severity`
- `category`
- `title`
- `description`
- `suggested_next_action`
- `status`

不要把有债务的任务伪装成 completed。

---

## 6. 审批与 checkpoint 对接

当前已有表：

- `agent_approval_queue`
- `agent_checkpoints`

需要把它们纳入 workflow 账本关联。

建议扩展字段：

### `agent_approval_queue`

增加或兼容：

- `workflow_run_id`
- `workflow_step_id`
- `tool_call_id`
- `payload_hash`
- `resume_target`

### `agent_checkpoints`

增加或兼容：

- `workflow_run_id`
- `workflow_step_id`
- `agent_run_id`

要求：

- 用户确认后能恢复到正确 run/step/tool。
- checkpoint 不只按 conversation_id 粗粒度查。
- 多 worker 下共享状态必须持久化，不能依赖进程内内存。

---

## 7. API 要求

所有 API 必须走统一响应：

```json
{ "success": true, "data": ..., "error": null }
```

建议新增或完善 Agent 模块内 API：

```text
GET  /api/modules/agent/workflows
GET  /api/modules/agent/workflows/{run_id}
GET  /api/modules/agent/workflows/{run_id}/timeline
POST /api/modules/agent/workflows/{run_id}/approve
POST /api/modules/agent/workflows/{run_id}/resume
POST /api/modules/agent/workflows/{run_id}/cancel
```

具体路径按现有 Agent router 风格实现。

权限：

- 普通用户只能看自己的 workflow。
- 管理员可看全部。
- 审批操作必须校验 owner / role。

---

## 8. 前端要求

只改 `modules/agent/frontend/`。

目标不是做复杂项目管理软件，而是给用户一个无感知但可信的“工作状态”视图。

最低要求：

1. 会话侧边栏或 Agent 主界面能看到当前任务状态。
2. 任务详情能展示：
   - 当前 6 类状态之一
   - 进度
   - 已完成步骤摘要
   - 需要确认的动作
   - 失败/部分完成原因
3. timeline 默认折叠技术细节，面向普通用户显示“已做了什么”。
4. 对 `partial` 明确提示“部分完成，还有遗留项”，不能显示成完全成功。
5. TypeScript 不准用 `any` 糊弄；接口字段要与后端真实返回一致。

---

## 9. 测试与验收

至少完成：

### 9.1 单元/后端测试

建议新增或补齐：

```text
modules/agent/backend/tests/test_workflow_service.py
modules/agent/backend/tests/test_workflow_api.py
```

覆盖：

- 创建 workflow run
- step 状态推进
- tool call 落账
- approval 关联 workflow_run_id / workflow_step_id / tool_call_id
- checkpoint 关联 workflow_run_id / workflow_step_id
- PASS_WITH_DEBT 映射为 `partial`，不是 `completed`
- 普通用户不能读他人 workflow

### 9.2 sandbox

更新：

```text
modules/agent/sandbox/test_module.py
```

要求 sandbox 能证明 Agent 模块 workflow 基础契约可用。

### 9.3 必跑命令

优先用项目工具台 MCP：

```text
brief
plan_task(module_key="agent")
worktree_guard(module_key="agent")
code_explore / code_node / code_impact
lint(path="modules/agent/...")
run_test(target="modules/agent/backend/tests/test_workflow_service.py")
run_test(target="modules/agent/backend/tests/test_workflow_api.py")
run_test(target="modules/agent/sandbox/test_module.py")
finish_task(module_key="agent")
memory_write(agent="codex-agent-workflow-ledger")
mcp_feedback(agent="codex-agent-workflow-ledger")
```

如果 MCP 临时不可用，可用等价本地命令，但交付报告里要说明。

---

## 10. 验收红线

以下情况判不通过：

1. 修改了 `backend/app/` 或 `frontend/src/`。
2. Agent 直接 import 其他模块业务代码。
3. Agent 直接读写 knowledge/memory/codemap 等其他模块业务表。
4. 纯内存保存 workflow 状态，重启或多 worker 后丢状态。
5. 有债务的任务显示为“已完成”。
6. API 不走统一响应。
7. 前端为了类型通过使用 `any` / `as any` / `@ts-ignore`。
8. 未跑相关测试或测试失败但报告写成成功。

---

## 11. 交付物

请交付：

1. 修改文件清单。
2. 新增表/字段说明。
3. API 列表和示例响应。
4. 6 状态映射说明。
5. 测试命令与结果。
6. 剩余风险。
7. 项目记忆：用 `memory_write(agent="codex-agent-workflow-ledger")` 写入。
8. MCP 反馈：用 `mcp_feedback(agent="codex-agent-workflow-ledger")` 写入。

---

## 12. 一句话目标

把 Agent 做成后端可恢复、可审计、可暂停继续的无感工作流中枢；用户只看得懂“等、做、确认、完成、失败、部分完成”。
