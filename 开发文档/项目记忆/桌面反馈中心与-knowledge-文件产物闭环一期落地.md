---
name: "桌面反馈中心与 Knowledge 文件产物闭环一期落地"
type: "task"
tags: [desktop, feedback-center, knowledge, product-loop, verification]
agent: "codex-product-loop-conductor"
created: "2026-07-04T04:39:32.965802+00:00"
---

## 我是谁

agent: codex-product-loop-conductor

## 做了什么

执行两封任务信：

- `执行信-桌面全局反馈中心第一期.md`
- `执行信-文件到知识库到产物用户闭环一期.md`

桌面侧：

- 在任务栏挂载反馈中心入口。
- `use-notifications` 聚合 `/api/notifications`、`/api/tasks/worker/audit`、`agent:list_workflows`。
- 任务栏 badge 改为反馈信号数：未读通知 + 后台任务运行/失败/债务 + Agent 待确认/失败/部分完成。
- 通知面板升级为“反馈中心”，分为需要处理、后台任务、Agent 工作、通知，使用等待中/处理中/需要确认/已完成/失败/部分完成的人话状态。

Knowledge 侧：

- 前端 API 增加 `getIngestStatus`、`exportDocument`、`getPendingCount`、`getGovernanceCandidates` 与明确类型。
- 文档详情页优先展示统一 `ingest-status`：当前阶段、search ready、deep ready、失败原因、source state、next action。
- 接入 Markdown/HTML/JSON 导出入口；源文件不可用或未 search ready 时禁用导出。
- source unavailable 显示人话解释：原始文件可能删除、回收、无权限或路径不可用；不再当普通 pending/completed 展示。
- 看板增加“源文件不可用”和“治理待办”入口，source unavailable 行不提供重新触发按钮，避免反复撞缺失源文件。

## 修改文件

- `frontend/src/desktop/taskbar/desktop-taskbar.vue`
- `frontend/src/desktop/taskbar/taskbar-notifications.vue`
- `frontend/src/shared/components/notification-panel.vue`
- `frontend/src/shared/composables/use-notifications.ts`
- `modules/knowledge/frontend/api.ts`
- `modules/knowledge/frontend/index.vue`
- `modules/knowledge/frontend/views/DashboardView.vue`

未修改 `backend/app/routers/tasks.py`、`backend/app/routers/notifications.py`、`modules/agent/`、`dev_toolkit/`。开工已有这些路径的 dirty，本轮按基线避开。

## 验证结果

- `cd frontend && npm run build`：通过。
- `cd modules/knowledge/sandbox && npm run build`：通过，仅 Vite chunk warning。
- `backend/.venv/bin/python -m pytest modules/knowledge/sandbox/test_module.py`：11 passed。
- TypeScript 压制扫描：本轮触碰范围无新增 `any/as any/@ts-ignore/@ts-expect-error`。
- Playwright 活栈：真实登录后点击任务栏反馈中心成功，面板显示“反馈中心 / 后台任务 / Agent 工作”。
- `probe GET /api/health`：200 success true。
- `probe GET /api/notifications`：200 success true，当前空列表。
- `probe GET /api/tasks/worker/audit`：200 success true，pending/running/failed 均 0，completed 161。
- `probe GET /api/knowledge/dashboard/stats`：200 success true，total 160，completed 2，failed/source_unavailable 158。
- `call_capability knowledge:get_pending_count {}`：success true，pending_count 2。
- `call_capability knowledge:get_ingest_status {document_id:40}`：success true，source_available true，search_ready/deep_ready true。
- `call_capability knowledge:get_ingest_status {document_id:159}`：success true，source_available false，source_state source_file_deleted。
- `call_capability knowledge:export {document_id:40, format:markdown}`：success true，返回 markdown 内容。
- `call_capability agent:list_workflows {limit:5}`：success true，当前 items 空。
- `finish_task`：边界通过，本轮 new_outside_allowed 0，new_forbidden_hits 0。

## 子代理分工

- 子代理 1：只读复核桌面反馈中心现状和通知/任务/Agent API，指出 badge 只看未读、缺 workflow 聚合。
- 子代理 2：只读给出桌面反馈中心实现建议和六类用户状态映射。
- 子代理 3：Knowledge 能力复核未及时返回，被关闭释放。
- 子代理 4：只读复核 Knowledge ingest/status/export 和前端闭环，确认 document_id=40 可导出、159 source_unavailable。
- 子代理 5：只读验收清单，提醒边界、类型压制、sandbox/build/capability 探针。
- 追加最终复核代理：只读复核本轮 diff 和风险。

## 残留风险

- 工作区开工已有大量并行 dirty，包含 backend/app、dev_toolkit、modules/agent、modules/knowledge/backend/services/chunking_service.py，本轮未覆盖也未清理。
- Knowledge 现有 158 条 source_unavailable 是真实历史数据债，本期只做可理解展示和入口，不清理数据。
- Agent workflow 当前真实列表为空，反馈中心已经空态兜底；产物直达入口仍依赖后续 workflow/artifact 字段补齐。

## 关联 commit

无。用户要求不要提交 git commit。
