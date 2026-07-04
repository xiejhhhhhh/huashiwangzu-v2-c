# 真实 Workflow 种子数据与 Agent 治理面板落地收口

## 结果

本轮完成 Agent workflow demo seed、cleanup、治理 summary、列表过滤和前端治理面板闭环。seed 是可重复、可清理的 admin-only 开发/演示机制，不创建框架文件，不写其他模块表，不污染 release gate。

## Seed 数据结构

默认 marker：`agent-demo-workflow`。自定义 marker 必须以 `agent-demo-` 或 `workflow-demo-` 开头。

每次 seed 创建 4 条 workflow：

| 场景 | 终态 | 内容 |
|---|---|---|
| completed | `completed` / `clean_completed` | research subagent、knowledge tool call、evidence references、report artifact、pass verification |
| partial | `partial` / `completed_with_debt` | repair subagent、patch artifact、release_gate `PASS_WITH_DEBT` verification |
| semantic failed | `failed` / `failed_verified` | writer subagent、failed `office-gen__write_ir` tool call、`semantic_failure` failure record、retry reason |
| needs confirmation | `needs_confirmation` | approval step、workspace write tool call、pending approval queue record |

所有 seed run 的 `source=demo_seed`，`title` 以 marker 开头，`extra_meta.demo_marker` 写入 marker，关联 artifact/step metadata 也带 marker。

## 清理方式

HTTP：

```text
POST /api/agent/workflows/demo-seed
POST /api/agent/workflows/demo-seed/cleanup
```

Capability：

```text
agent:seed_demo_workflows
agent:cleanup_demo_workflows
```

cleanup 按 marker 删除：

```text
agent_approval_queue
agent_failure_records
agent_verification_results
agent_workflow_artifacts
agent_tool_calls
agent_workflow_steps
agent_workflow_runs
```

活栈验证 marker `agent-demo-live-20260704` 已创建 4 条并 cleanup，SQL 残留计数为 0。

## 治理面板

后端新增：

| 能力 | 说明 |
|---|---|
| workflow list filters | 支持 `status` / `has_failures` / `has_artifacts` / `has_references` |
| workflow detail | 返回 steps、tool calls、artifacts、verifications、failures、summary counts、multi-agent summary |
| governance summary | 返回 total、failed、partial、completed、needs_confirmation、with_artifacts、with_references、average_duration_ms、recent_errors |

前端治理面板新增：

| 区域 | 变化 |
|---|---|
| WorkflowList | 顶部统计、全部/失败/需确认/有产物/有引用筛选、真实 rollup 计数、复制 workflow id |
| WorkflowDetail | 展示完整 ledger、semantic failure reason、复制 workflow id、复制错误 |
| EvidenceReferenceList | 继续支持引用复制和文件型引用打开 |

## 验证结果

```text
ruff check changed agent backend files: PASS
pytest modules/agent/backend/tests/test_workflow_service.py: 13 passed
pytest modules/agent/backend/tests/test_workflow_api.py: 7 passed
npm --prefix frontend run build: PASS
release_gate(skip_ui=true, mode=preflight): PASS_WITH_DEBT, no BLOCKER
```

release gate 债务均为本次指定 preflight/skip-ui 和既有 dirty worktree 口径：UI coverage skipped、smoke skipped、Playwright skipped、model fallback skipped、sandbox matrix skipped、dirty files。Capability drift 已在后端重启后清零：manifest/live/source 均为 189。

活栈 capability 验证：

```text
agent:seed_demo_workflows(marker=agent-demo-live-20260704): created 4
agent:get_workflow_governance_summary: total 4, failed 1, partial 1, completed 1, needs_confirmation 1
agent:list_workflows(has_failures=true): semantic_failure sample visible with reason
agent:cleanup_demo_workflows(marker=agent-demo-live-20260704): deleted 4
SQL marker residual count: 0
```

## 剩余风险

- 本轮前端 build 已过，但没有额外跑 Playwright UI 截图验收；release gate 因 `skip_ui=true` 按规则记录为 debt。
- 工作区已有大量其他未提交改动，本轮只在 Agent workflow 相关范围内叠加；收尾仍需按基线区分。
- Demo artifacts 使用 inline metadata，不创建真实框架文件；这是为了可清理和不污染 gate，真实文件型 artifact 仍需由生产 workflow 自己产生。
