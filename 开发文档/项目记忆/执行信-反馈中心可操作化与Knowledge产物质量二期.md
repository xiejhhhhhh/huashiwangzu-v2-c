# 执行信：反馈中心可操作化与 Knowledge 产物质量二期

收件人：Codex / 独立执行会话  
任务类型：产品闭环二期 / 桌面反馈中心 + Knowledge 产物质量  
建议 agent 标识：`codex-feedback-knowledge-product-r2`  
优先级：高  
执行方式：目标模式优先；可以使用最多 5 个子代理并行侦查/实现/验收，子代理做完即释放  
核心边界：**聚焦反馈中心 ActionItem 可操作化 + Knowledge 导出/状态/source unavailable 收口，不做大范围重构**

---

## 0. 任务一句话

把一期已经完成的“看见状态”升级成二期的“能处理问题”：反馈中心里的通知、任务、Agent workflow、Knowledge 问题要能跳转、重试、归档或给出明确下一步；Knowledge 导出要变成可信产物，状态口径要一致，source unavailable 要从“解释”升级为“可处理”。

---

## 1. 必读材料

请先读：

1. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/AGENTS.md`
2. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/README.md`
3. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/01_框架开发文档/README.md`
4. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/03_模块开发文档/README.md`
5. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/knowledge/README.md`
6. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/桌面反馈中心与-knowledge-文件产物闭环一期最终验收补充.md`
7. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/验收桌面反馈中心与-knowledge-闭环一期并判断下一步.md`
8. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/产品化闭环桌面体验与测试发布效率总审计报告.md`
9. `/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/AI-Agent能力上限与成熟工作台对标调研报告.md`

开工先确认当前工作区状态。当前可能还有一期收尾的 3 个 dirty 文件：

```text
frontend/src/shared/components/notification-panel.vue
开发文档/项目记忆/桌面反馈中心与-knowledge-文件产物闭环一期最终验收补充.md
开发文档/项目记忆/工具台反馈-20260704-045012-codex-product-loop-conductor-执行桌面全局反馈中心一期与-knowledge-文件到知识库到产物用户闭.md
```

如果这些文件仍未提交，请把它们视为一期基线的一部分，不要回滚；在此基础上继续做二期。

---

## 2. 当前审计结论

一期已经完成：

- 桌面任务栏接入反馈中心入口。
- 反馈中心聚合 notifications、任务审计、Agent workflow 信号。
- Knowledge 前端接入 ingest status、source unavailable、问 AI 预填、Markdown/HTML/JSON 导出、治理待办计数与候选提示。
- `cancelled/canceled` 状态已补为“已取消”。
- 已验证：前端 build、Knowledge sandbox build、Knowledge sandbox pytest、TS 绕过扫描、git diff check、关键 probe/capability。

但审计发现二期必须解决的问题：

1. **反馈中心只做到“看见”，还没有做到“可处理”。**
   - 用户能看到失败、待确认、部分完成，但不一定能一键跳到对应任务、文档、workflow 或修复动作。
2. **反馈项没有统一 ActionItem 契约。**
   - 通知、任务、Agent workflow、Knowledge 文档问题各自展示，缺少统一字段：主操作、次操作、跳转目标、是否可重试、是否可归档。
3. **Knowledge 导出能用，但产物质量还不够可信。**
   - chunk 与 fusion 可能重复导出。
   - export format 后端校验偏松，前端限制不能代替后端契约。
4. **Knowledge 状态口径还有轻微不一致。**
   - graph stage 在无实体样本下展示略不一致。
   - 用户想知道的是“这份文档是否可搜索、可深度分析、可导出、可形成图谱”，不是内部表状态。
5. **source unavailable 现在能解释，但还不能恢复。**
   - 用户看到源文件不可用，但没有足够明确的“重新绑定 / 从回收站恢复 / 归档删除无效记录”闭环。
6. **Agent 问 AI 入口还偏 prefill。**
   - 应该尽量携带 documentId、文档状态、searchReady/deepReady 等上下文，让 Agent 明确“基于哪份资料提问”。

---

## 3. 总目标

本任务只追一个目标：

> 用户在反馈中心或 Knowledge 页面看到问题后，不需要猜下一步，系统要给出明确可执行动作；用户导出知识库内容时，产物要可信、格式明确、错误清楚。

可拆成 5 个目标。

---

## 4. 目标一：建立反馈中心 ActionItem 契约

### 4.1 目标

把反馈中心里的不同信号统一成可操作项：

```text
通知
后台任务
Agent workflow
Knowledge 文档状态/治理问题
```

每个 ActionItem 至少要有：

```text
id
source_type          notification / task / agent_workflow / knowledge_document / knowledge_governance
source_id
title
description
severity             info / warning / error / success
visible_status       等待中 / 处理中 / 需要确认 / 已完成 / 失败 / 部分完成 / 已取消
action_label         主操作按钮文案
action_target        要打开的模块/页面/对象
action_payload       跳转所需参数
secondary_actions    可选：重试、忽略、归档、查看详情
can_retry
can_archive
created_at / updated_at
```

实现不要求新建后端表。第一版可以在前端聚合层把已有 API 响应规整为 ActionItem。

### 4.2 验收标准

- 反馈中心代码里有清晰的 ActionItem 类型定义。
- 通知、任务审计、Agent workflow、Knowledge 问题至少 3 类来源能映射成 ActionItem。
- 空状态、失败状态、已取消状态都显示正常。
- 不使用 `any/as any/@ts-ignore/@ts-expect-error`。

---

## 5. 目标二：反馈中心支持深链跳转和下一步动作

### 5.1 目标

用户看到 ActionItem 后，可以执行明确动作。

至少支持：

1. **打开 Agent workflow**
   - 如果 ActionItem 来源是 Agent workflow，应能打开 Agent 模块，并带上 workflow/run/conversation 相关上下文。
   - 如果当前 Agent 前端还没有精确详情跳转，就先打开 Agent 模块并传 payload；不要硬造不可用路由。

2. **打开 Knowledge 文档**
   - 如果来源是 Knowledge 文档或治理问题，应打开 Knowledge 模块并尽量定位到对应 document。
   - 如果当前模块只能打开首页，也要带上 payload 供后续消费。

3. **打开任务来源或详情**
   - 如果任务审计里有 handler/source/module 信息，应显示“查看任务/查看来源模块”。
   - 没有明确目标时，显示保守文案，不要假跳转。

4. **归档/忽略动作**
   - 对本地前端聚合项可以先做“本地本次忽略/折叠”，不要求后端持久归档。
   - 如果已有 notification read/clear API，则可调用真实接口。

### 5.2 验收标准

- 点击主操作不会白屏。
- 无目标 payload 时不显示假按钮。
- 至少能从反馈中心跳到 Knowledge 和 Agent 模块。
- 操作文案是用户语言，不暴露 `workflow_run_id/tool_call_id/raw status`。

---

## 6. 目标三：Knowledge 导出产物质量收口

### 6.1 目标

Knowledge 导出必须从“能导出”升级为“可信产物”。

必须完成：

1. **后端 format 强校验**
   - 只允许：`markdown`、`html`、`json`。
   - 非法 format 返回统一错误，不要静默降级为 markdown。

2. **导出内容去重**
   - 检查 chunk 与 fusion 同时导出造成重复的问题。
   - 设计并实现简单明确的去重策略，例如：
     - 优先 page fusion；
     - fusion 缺失时用 chunks；
     - 或按 block hash 去重。
   - 报告里说明采用哪种策略。

3. **导出元数据明确**
   - 导出结果中应能说明：
     - document_id；
     - title；
     - format；
     - source_status；
     - search_ready/deep_ready；
     - block_count 或 evidence_count。

4. **前端导出失败提示**
   - 导出失败时显示用户可懂错误。
   - 不要只 toast “失败”。

### 6.2 验收标准

- `knowledge:export` 对 markdown/html/json 都成功。
- 非法 format 明确失败，且外层统一响应正确。
- 导出内容不明显重复。
- 前端导出按钮对不可导出状态有合理禁用或提示。

---

## 7. 目标四：Knowledge 状态语义统一

### 7.1 目标

统一 Knowledge 用户状态，不让用户理解内部 pipeline 表。

建议前端最终只表达这些语义：

```text
源文件可用 / 源文件不可用
可搜索 / 不可搜索
可深度分析 / 不可深度分析
可导出 / 不可导出
图谱可用 / 图谱暂无数据
存在治理待办 / 无治理待办
```

后端 ingest status 可以继续保留 stage 细节，但前端需要映射成用户语义。

### 7.2 graph stage 特别要求

无实体样本时，不要让用户误解为系统失败。

文案建议：

```text
图谱暂无数据：当前文档未抽取到可用实体或关系，不影响搜索和导出。
```

只有真正 pipeline 错误时才显示失败。

### 7.3 验收标准

- `/api/knowledge/dashboard/stats` 中大量 source unavailable 不会让整个 Knowledge 首页像系统崩了。
- 单文档 ingest status 能清楚显示“可搜索/可导出/图谱暂无数据/源文件不可用”。
- graph 无实体不应被显示成致命失败。

---

## 8. 目标五：source unavailable 从解释升级为处理路径

### 8.1 目标

source unavailable 当前已经能解释，但还要给出可执行处理路径。

至少实现其中两类真实动作或准动作：

1. **归档/删除无效知识记录**
   - 如果已有删除/归档能力，接上入口。
   - 没有持久归档能力时，先做“建议操作 + 跳转/确认”，不要假装已经处理。

2. **从回收站恢复源文件**
   - 如果能判断源文件在回收站，提供跳转到回收站/文件管理器的入口。
   - 如果无法判断，显示“可能在回收站，请到文件管理器检查”。

3. **重新上传/重新绑定源文件**
   - 最低要求：提供重新上传入口或明确引导。
   - 如果能保留 document_id 并重新绑定，优先做真实绑定；如果做不到，不要假实现。

### 8.2 验收标准

- source unavailable 文档页面有明确下一步按钮或指引。
- 不允许只有一段解释文字，没有动作。
- 不允许点击按钮后无效果或白屏。
- 不允许直接删除用户数据，删除/归档必须有确认。

---

## 9. 修改边界

### 9.1 允许修改

```text
frontend/src/shared/components/notification-panel.vue
frontend/src/shared/composables/use-notifications.ts
frontend/src/shared/api/
frontend/src/desktop/taskbar/
modules/knowledge/frontend/
modules/knowledge/backend/router.py
modules/knowledge/backend/services/
modules/knowledge/backend/schemas.py
modules/knowledge/sandbox/
modules/knowledge/README.md
开发文档/项目记忆/
```

### 9.2 谨慎修改

```text
backend/app/routers/notifications.py
backend/app/routers/tasks.py
```

原则：本任务尽量不改这两个后端框架 router。只有发现无法实现必要 ActionItem 数据，且必须补一个稳定公共字段时，才允许最小修改，并必须写清楚原因和兼容性。

### 9.3 禁止修改

```text
modules/agent/backend/workflow_models.py
modules/agent/backend/services/workflow_service.py
modules/agent/backend/runtime/
modules/agent/frontend/components/Workflow*.vue
dev_toolkit/release_gate.py
dev_toolkit/smoke.py
dev_toolkit/module_sandbox_matrix.py
backend/.venv
frontend/node_modules
```

本任务不要做 Agent runtime 可靠性专项，不要做测试发布分层专项。

---

## 10. 子代理建议分工

如果使用 5 个子代理，建议：

1. **子代理 1：反馈中心现状复核**
   - 读 notification panel、use-notifications、任务栏入口。
   - 输出 ActionItem 类型和映射建议。

2. **子代理 2：反馈中心实现**
   - 实现 ActionItem 聚合、状态文案、主操作按钮、空状态和错误状态。

3. **子代理 3：Knowledge 导出质量复核**
   - 读 export service/router/schema/frontend 调用。
   - 找出 format 校验、重复内容、错误返回问题。

4. **子代理 4：Knowledge 状态/source unavailable 实现**
   - 实现状态语义映射、source unavailable 动作、graph 暂无数据文案。

5. **子代理 5：验收与边界复核**
   - 跑 build/test/probe/capability。
   - 扫 TS any/as any。
   - 检查 git diff 边界。

子代理做完即释放，不要长期占格子。

---

## 11. 必跑验证

### 11.1 前端

```text
cd frontend && npm run build
```

如改了 Knowledge sandbox：

```text
cd modules/knowledge/sandbox && npm run build
```

### 11.2 后端 / 模块测试

```text
backend/.venv/bin/python -m pytest modules/knowledge/sandbox/test_module.py
```

如新增后端服务测试，补跑对应 pytest。

### 11.3 活系统 probe

必须验证：

```text
GET /api/health
GET /api/notifications
GET /api/tasks/worker/audit
GET /api/knowledge/dashboard/stats
```

### 11.4 capability

必须验证：

```text
knowledge:get_pending_count
knowledge:get_ingest_status
knowledge:export     # markdown/html/json
agent:list_workflows # 只读，允许为空
```

必须验证非法导出格式：

```text
knowledge:export(format="bad_format") 应明确失败
```

### 11.5 静态检查

必须做：

```text
git diff --check
```

并扫描目标前端文件中是否出现：

```text
any
as any
@ts-ignore
@ts-expect-error
```

不得新增这些绕过。

---

## 12. 验收红线

以下情况判不通过：

1. 反馈中心仍只能看，不能点到任何有效下一步。
2. ActionItem 字段混乱，通知/任务/Agent/Knowledge 各自写一套不可维护逻辑。
3. Knowledge export 非法 format 被静默当成 markdown。
4. 导出内容明显重复但未处理或未说明。
5. source unavailable 只有解释，没有动作或指引。
6. graph 无实体被显示成系统失败。
7. 前端新增 `any/as any/@ts-ignore/@ts-expect-error`。
8. 越界修改 Agent runtime、dev_toolkit release gate、smoke、sandbox matrix。
9. 删除或清理真实用户数据来制造健康。
10. 测试失败却报告成功。

---

## 13. 交付物

请交付：

1. 修改文件清单。
2. ActionItem 契约说明。
3. 反馈中心支持哪些来源、哪些动作、哪些跳转。
4. Knowledge 导出 format 校验和去重策略说明。
5. Knowledge 用户状态语义映射说明。
6. source unavailable 的可执行处理路径说明。
7. 验证命令与真实结果。
8. 失败项、跳过项、剩余风险。
9. `memory_write(agent="codex-feedback-knowledge-product-r2")`。
10. `mcp_feedback(agent="codex-feedback-knowledge-product-r2")`。

---

## 14. 最终目标口径

完成后，用户体验应达到：

- 用户看到反馈中心，不只是知道“有问题”，还能点进去处理。
- 用户看到 Knowledge 文档，不只是知道“失败/不可用”，还能知道能不能搜索、能不能导出、能不能问 AI、下一步怎么恢复。
- 用户导出的 Markdown/HTML/JSON 是可信产物，不重复、不静默降级、失败有明确原因。
- 一期的“产品可见”升级为二期的“产品可操作”。
