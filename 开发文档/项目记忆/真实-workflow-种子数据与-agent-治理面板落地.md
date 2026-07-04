---
name: "真实 Workflow 种子数据与 Agent 治理面板落地"
type: "task"
tags: [agent, workflow, seed, governance, cleanup, verification]
agent: "codex-workflow-seed-governance"
created: "2026-07-04T13:40:35.258643+00:00"
---

# 做了什么

- 新增 `modules/agent/backend/services/workflow_seed_service.py`，提供 admin-only demo seed/cleanup，默认 marker `agent-demo-workflow`，自定义 marker 必须以 `agent-demo-` 或 `workflow-demo-` 开头。
- Seed 创建 completed、partial、semantic failed、needs_confirmation 四类真实 workflow 账本样本，包含 steps、tool calls、evidence references、artifacts、verification、failure records 和 approval queue。
- 新增/扩展 workflow API 与 capability：`get_workflow_governance_summary`、`seed_demo_workflows`、`cleanup_demo_workflows`，list 支持 `status` / `has_failures` / `has_artifacts` / `has_references` 过滤。
- Workflow detail 返回 steps、tool_calls、artifacts、verifications、failures、rollup counts 和 multi_agent_summary；普通用户仍只看自己 workflow，tool arguments 仅 admin 展开。
- 前端治理面板新增 summary 统计、筛选按钮、真实 rollup 计数、复制 workflow id、复制错误；README 写入稳定用法，执行信内容收口到 `开发文档/项目记忆/真实Workflow种子数据与Agent治理面板落地收口.md`，原执行信已删除。

# 验证了什么

- ruff changed agent backend files: PASS。
- `modules/agent/backend/tests/test_workflow_service.py`: 13 passed。
- `modules/agent/backend/tests/test_workflow_api.py`: 7 passed。
- 合跑 `test_workflow_service.py test_workflow_api.py`: 20 passed。
- `npm --prefix frontend run build`: PASS。
- 后端重启后 `release_gate(skip_ui=true, mode=preflight)`: PASS_WITH_DEBT，无 BLOCKER，capability drift 清零 manifest/live/source=189。
- 活栈 capability 验证：`seed_demo_workflows(marker=agent-demo-live-20260704)` 创建 4 条；summary 显示 total 4、failed 1、partial 1、completed 1、needs_confirmation 1；`list_workflows(has_failures=true)` 可见 semantic_failure reason；`cleanup_demo_workflows` 删除 4 条；SQL marker 残留 count=0。

# 残留风险

- release gate 债务来自本次指定 preflight/skip-ui、未跑完整 smoke/UI/sandbox，以及工作区已有大量外部 dirty；无 BLOCKER。
- 工作区存在许多其他 agent/模块/框架并行改动，未归属本轮，未回退。

# 关联 commit

未提交。
