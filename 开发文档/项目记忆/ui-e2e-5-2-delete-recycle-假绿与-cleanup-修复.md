---
name: "UI e2e 5.2 delete/recycle 假绿与 cleanup 修复"
type: "task"
tags: [ui-e2e, recycle, cleanup, post-convergence]
agent: "codex-post-convergence-ui-worker"
created: "2026-07-03T17:55:27.642157+00:00"
---

# 改了什么
- 仅修改 `frontend/tests/ui-e2e.spec.mjs`。
- `readActiveFileItems` / `readRecycleItems` 改为 fail-closed：HTTP 失败、统一响应 `success !== true`、返回数据非数组都会 throw，避免查询失败被空数组吞掉导致 delete 假绿。
- 5.2 `passed` 现在包含完整链路：`uploadVisible`、`deletedByApi`、`deleteState.deleted`、`deleteState.inRecycle`、`restored`、`restoredActiveVisible`、`recycleGoneAfterRestore`。
- restore 继续使用 `RecycleItem.id + item_type`，并在 notes 中明确 `fileId/recycleItemId/originId`。
- cleanup 记录本轮上传 `fileId/fileName`，先软删 active 文件，再拉回收站，对本轮 `recycleItemId` 调 `/api/recycle/delete-permanently`，并轮询确认本轮 recycle items 消失；失败会让 cleanup 红，不再固定 passed=true。

# 验证了什么
- `node --check frontend/tests/ui-e2e.spec.mjs` 通过。
- `cd frontend && npx playwright test tests/ui-e2e.spec.mjs -g "5.2 File management - delete and recycle" --reporter=line` 通过。
- `cd frontend && npx playwright test tests/ui-e2e.spec.mjs -g "5.2 File management - delete and recycle|Delete all e2e test files" --reporter=line` 2/2 通过。
- `/api/health` probe 返回 200/status ok。

# 残留风险
- 未跑全量 UI，原因是本任务要求优先验证相关 5.2 场景，全量较慢。
- 工作区同时有并行代理修改 `backend/` 与 `dev_toolkit/`，本轮未触碰这些文件。

# 关联 commit
- 未提交。
