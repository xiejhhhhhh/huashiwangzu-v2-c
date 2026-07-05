---
name: "工具台反馈-20260705-075652-codex-CleanReleaseDebt 队列归档与 SandboxWarnin"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-05T07:56:52.229646+00:00"
---

# MCP 使用反馈

## 任务

CleanReleaseDebt 队列归档与 SandboxWarning 清零收口

## 顺畅度

- 评分：3/5
- 体感：前半程工具台可用，长任务后 MCP transport closed；CLI/本地函数兜底完成。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, db_schema, probe, memory_write(失败), local memory_tools/mailbox_tools

## 卡点 / 不顺手的地方

tool_job_submit 长任务后 MCP transport closed，memory_write/mailbox_create_delivery_bundle 无法通过 MCP 收尾。

## 缺少的工具 / 能力

需要工具台长任务与 stdio server 隔离，避免 release_gate/job 关闭 transport。

## 升级建议

mailbox/memory 工具建议提供官方 CLI 兜底入口。

## 建议移除或合并的工具

无

## 其他备注

本次因外部 dirty 无法达成 full gate clean。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 67,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "run_test",
    "calls": 64,
    "error": 0,
    "avg_duration_seconds": 3.218
  },
  {
    "tool": "probe",
    "calls": 63,
    "error": 3,
    "avg_duration_seconds": 0.263
  },
  {
    "tool": "code_impact",
    "calls": 36,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 32,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "lint",
    "calls": 29,
    "error": 0,
    "avg_duration_seconds": 0.093
  },
  {
    "tool": "sql",
    "calls": 25,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_explore",
    "calls": 18,
    "error": 1,
    "avg_duration_seconds": 0.349
  },
  {
    "tool": "finish_task",
    "calls": 17,
    "error": 0,
    "avg_duration_seconds": 1.344
  },
  {
    "tool": "capabilities",
    "calls": 15,
    "error": 0,
    "avg_duration_seconds": 0.001
  }
]
```
