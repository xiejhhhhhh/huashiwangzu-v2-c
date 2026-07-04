# 执行信：Agent 工具调用可靠性与失败恢复专项

收件人：Codex / 独立执行会话
任务类型：Agent 能力增强
建议 agent 标识：`codex-agent-tool-reliability-r1`
优先级：高，但需要先检查依赖
边界：优先在 `modules/agent/` 内做；如果 Agent workflow 中枢仍未稳定合并，则只做不冲突的小范围 runtime 失败分类，避免抢 workflow 文件。

---

## 0. 任务一句话

把 Agent 工具调用从“能调工具”升级为“失败可分类、可落账、可恢复、可验证、可向用户解释”。

---

## 1. 必读材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/03_模块开发文档/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/agent/README.md`
5. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/AI-Agent能力上限与成熟工作台对标调研报告.md`
6. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/后端无感-agent-工作流中枢落地.md`，如存在
7. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/验收-agent-workflow-中枢并写入二阶段执行信.md`，如存在

---

## 2. 依赖判断

开始前必须判断当前 Agent workflow 中枢是否已经基本完成并稳定：

```text
git status --short modules/agent
capabilities(module="agent")
call_capability(agent:list_workflows)
probe(GET /api/agent/workflows?limit=5)
```

如果发现 `modules/agent/` 仍在大量施工，且 workflow 主链文件未稳定，不要继续大改。本任务可降级为只读复核和小修执行信，不要抢文件。

---

## 3. 修改边界

### 允许修改

```text
modules/agent/backend/runtime/
modules/agent/backend/engine/
modules/agent/backend/services/
modules/agent/backend/tests/
modules/agent/sandbox/
modules/agent/README.md
开发文档/项目记忆/
```

### 谨慎修改

```text
modules/agent/backend/services/workflow_service.py
modules/agent/backend/handlers/workflow.py
modules/agent/backend/workflow_models.py
```

只有确认 Agent workflow 中枢已完成且当前没有并行冲突时，才允许最小修改。

### 禁止修改

```text
backend/app/
frontend/src/
modules/knowledge/
modules/memory/
modules/codemap/
dev_toolkit/
```

---

## 4. 背景证据

AI Agent 能力调研结论：

- 当前 Agent 成熟度约 6.4/10。
- 最短板包括：workflow 主链绑定、失败恢复、验证闭环、多 Agent 治理、产物发布闭环。
- 工具调用已有 ToolGate、ToolOrchestrator、渐进式工具发现、慢工具投队列。
- 但工具失败后的重试策略、替代工具、降级路径和 Problem Matcher 不够结构化。
- stuck 后更多是停止/记录，缺“失败归因 → 换模型/换工具/缩小目标/请求确认/转人工”的状态机。

---

## 5. 功能目标

### 5.1 失败分类标准化

将工具失败至少分类为：

```text
validation_error       参数/输入不合法
auth_error             权限/登录/角色不足
not_found              文件/资源不存在
rate_limited           限流/配额
timeout                超时
transient_error        网络/临时服务错误
external_service_error 外部服务失败
unsafe_action          安全策略拒绝
unknown_error          未知错误
```

每类应有：

- 用户可懂摘要；
- 是否可重试；
- 建议下一步；
- 是否需要用户确认；
- 是否应进入 workflow failure record。

### 5.2 工具调用落账与结果引用

如果 workflow 主链已稳定：

- 工具开始、成功、失败都要落账；
- 失败要有 error_signature；
- 大结果只存摘要或 result_ref，不把长输出塞满上下文；
- `PASS_WITH_DEBT` 不得显示为 clean completed。

如果主链未稳定：

- 只做 runtime 层的 failure normalization，不碰 workflow 表结构和 handler。

### 5.3 恢复策略

实现或补齐最小恢复策略：

- 可重试错误：有限次数重试，带 backoff；
- 参数错误：请求模型修正参数一次；
- 权限错误：进入需要确认/无权限说明，不重复撞；
- not found：提示用户重新选择/上传；
- timeout：转慢任务或提示后台继续；
- unsafe action：走 approval，不自由重写危险动作。

### 5.4 Problem Matcher 雏形

至少为常见输出建立结构化解析雏形：

- pytest failure；
- ruff/lint error；
- probe/call_capability failure；
- terminal non-zero exit。

输出结构建议：

```text
source
title
message
severity
file_path
line
suggested_action
raw_excerpt
```

不要追求一次性覆盖所有工具。

---

## 6. 测试与验收

必须新增或补齐测试，覆盖：

1. failure 分类；
2. retryable 判断；
3. unsafe action 不自由重试；
4. pytest/ruff/probe 输出解析；
5. 工具失败进入 failure record 或明确返回 manual_required；
6. 不把失败包成成功。

建议命令：

```text
lint(path="modules/agent/backend/runtime,modules/agent/backend/engine,modules/agent/backend/services")
run_test(target="modules/agent/backend/tests/test_workflow_runtime_link.py")
run_test(target="modules/agent/backend/tests/test_workflow_service.py")
run_test(target="modules/agent/sandbox/test_module.py")
```

按实际新增测试文件调整。

---

## 7. 不做事项

本任务不要做：

1. 不实现多 Agent work item 系统。
2. 不做产物发布工作台。
3. 不重做 workflow 表结构。
4. 不改框架任务队列。
5. 不改其他模块能力实现。
6. 不把所有失败都自动重试，避免放大副作用。
7. 不把危险动作改写成“看起来安全”的动作绕过审批。

---

## 8. 验收红线

以下直接判不通过：

- 工具失败被包装为 success。
- 危险动作失败后自由重试，没有 payload_hash/resume_target。
- 直接 import 其他模块代码。
- 修改 `backend/app/` 或其他模块。
- 无测试覆盖失败分类和恢复策略。
- 当前 workflow 中枢仍在施工时强行改同一批文件造成冲突。

---

## 9. 交付物

请交付：

1. 当前 workflow 中枢依赖判断结果。
2. 修改文件清单。
3. failure taxonomy 说明。
4. retry / manual_required / unsafe_action 状态机说明。
5. Problem Matcher 覆盖范围。
6. 测试命令与结果。
7. 剩余风险。
8. `memory_write(agent="codex-agent-tool-reliability-r1")`。
9. `mcp_feedback(agent="codex-agent-tool-reliability-r1")`。

---

## 10. 一句话目标

Agent 不只是会调用工具，而是工具失败时知道为什么、怎么办、能不能重试、是否要问用户，并能把这些证据写进工作流。
