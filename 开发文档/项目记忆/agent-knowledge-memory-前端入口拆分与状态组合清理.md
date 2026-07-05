---
name: "Agent Knowledge Memory 前端入口拆分与状态组合清理"
type: "task"
tags: [frontend, agent, knowledge, memory, refactor, entry-split]
agent: "codex"
created: "2026-07-05T07:03:54.396812+00:00"
---

# 改了什么

执行平台健壮性任务：把 Agent / Knowledge / Memory 三个 AI 类模块的前端入口拆成入口布局 + composable + api/types 结构。

- Agent: `frontend/index.vue` 降到 161 行；新增 `useAgentChat.ts`、`messageSanitizer.ts`、`types/index.ts`、`api/index.ts`、`api/conversations.ts`。保留现有对话、编辑重发、SSE、工作轨迹和 admin panel 行为。
- Knowledge: `frontend/index.vue` 降到 510 行；新增 `useKnowledgeWorkspace.ts`、`types/index.ts`。保留文件树、自动登记、补跑、轮询、搜索、导出、问 AI 和图谱/看板入口行为。
- Memory: 保持 stub UI；新增 `useMemoryOverview.ts`、`api/index.ts`、`types/index.ts`，为后续概览/列表 UI 铺结构。
- 三个模块 README 增加 Frontend Structure 说明。

# 验证了什么

- `npm --prefix frontend run build` 通过。
- `rg "\bany\b|as any|@ts-ignore|@ts-expect-error" modules/agent/frontend modules/knowledge/frontend modules/memory/frontend` 无命中。
- `git diff --cached --check` 通过。
- `PLAYWRIGHT_EXTERNAL_SERVER=1 npm --prefix frontend run test:browser -- --reporter=line` 结果为 41 passed, 1 failed, 5 did not run；失败在 `tests/ui-e2e.spec.mjs` 的文件删除/回收流程，错误为 `Session expired, please login again`，不是本次 Agent/Knowledge/Memory 入口拆分点；Agent/Memory/Knowledge 打开应用场景已经跑过。

# 残留风险

收工时工作区存在未暂存外部改动：`dev_toolkit/README.md`、`dev_toolkit/release_gate.py`、`dev_toolkit/release_gate/`、`frontend/tests/ui-e2e.spec.mjs`、`frontend/tests/ui-e2e/`。这些不是本任务提交内容，未 stage，导致全工作区不干净；本任务提交范围干净。

# 关联 commit

`1c26f0ec refactor: split ai module frontend entries`
