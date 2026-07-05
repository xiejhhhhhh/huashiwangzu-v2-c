---
name: "工具台反馈-20260705-083229-codex-clean-release-debt-CleanReleaseDebt 队列归档与 SandboxWarnin"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-clean-release-debt"
created: "2026-07-05T08:32:29.859062+00:00"
---

# MCP 使用反馈

## 任务

CleanReleaseDebt 队列归档与 SandboxWarning 收口续跑，修复 smoke Z1 active_failed 口径并验证 full gate 剩余 UI blocker。

## 顺畅度

- 评分：3/5
- 体感：MCP transport 持续 closed；本地 CLI、CodeGraph CLI 和本地 helper 可完成任务。

## 本次用到的工具

codegraph CLI, ruff, pytest, release_gate CLI, local memory_tools, local mailbox_tools

## 卡点 / 不顺手的地方

project_toolkit MCP brief/plan_task/worktree_guard/memory_write/mcp_feedback 均 Transport closed；rg 未排除 dev_toolkit/memory_embeddings.json 时输出极大。

## 缺少的工具 / 能力

希望在 MCP 断连时有一条等价的本地 finish_task CLI。

## 升级建议

给 rg/搜索类工具默认排除 memory_embeddings.json 等大缓存文件；release gate 可输出 latest JSON 到固定路径，方便交付引用。

## 建议移除或合并的工具

无

## 其他备注

提交 d8051f73；full gate 当前被 UI E2E 5.3 重复超时阻塞，队列和 sandbox 均已收口。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.143
  },
  {
    "tool": "probe",
    "calls": 81,
    "error": 3,
    "avg_duration_seconds": 0.268
  },
  {
    "tool": "run_test",
    "calls": 67,
    "error": 0,
    "avg_duration_seconds": 3.117
  },
  {
    "tool": "code_impact",
    "calls": 46,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 39,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "sql",
    "calls": 37,
    "error": 6,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "lint",
    "calls": 32,
    "error": 0,
    "avg_duration_seconds": 0.086
  },
  {
    "tool": "call_capability",
    "calls": 28,
    "error": 0,
    "avg_duration_seconds": 0.524
  },
  {
    "tool": "code_explore",
    "calls": 24,
    "error": 1,
    "avg_duration_seconds": 0.347
  },
  {
    "tool": "finish_task",
    "calls": 23,
    "error": 0,
    "avg_duration_seconds": 1.059
  }
]
```
