---
name: "提交反馈中心与 Knowledge 产物质量二期并写入资产生命周期执行信"
type: "task"
tags: [commit, verification, desktop, knowledge, asset-lifecycle]
agent: "codex"
created: "2026-07-04T08:16:31.849111+00:00"
---

# 改了什么

验收并准备提交反馈中心可操作化与 Knowledge 产物质量二期改动；基于流程能力审计报告写入下一封执行信：`开发文档/项目记忆/执行信-资产生命周期总收口与测试污染门禁.md`。

# 验证了什么

- ruff: `modules/knowledge/backend/router.py`、`modules/knowledge/backend/services/export_service.py` 通过。
- pytest: `modules/knowledge/sandbox/test_module.py` 14 passed。
- `cd frontend && npm run build` 通过，仅 chunk warning。
- `cd modules/knowledge/sandbox && npm run build` 通过，仅既有 Rollup/chunk warning。
- `git diff --check` 通过。
- probe `/api/health`、`/api/notifications`、`/api/tasks/worker/audit`、`/api/knowledge/dashboard/stats` 均成功。
- capability `knowledge:get_pending_count`、`agent:list_workflows` 成功。
- `release_gate(skip_ui=true, mode=preflight)` 为 PASS_WITH_DEBT，无 BLOCKER；`smoke_all(skip_ui=true)` 28/29 通过，UI 跳过。

# 是否还有残留风险

未跑 full UI；Knowledge/Content 生命周期债务仍存在：`kb_documents` active 中 163 个 source deleted，ContentPackage active 中 198 个 source deleted；测试文件污染仍在。这些已写入下一封执行信。

# 关联 commit

待本轮提交后补充提交哈希。
