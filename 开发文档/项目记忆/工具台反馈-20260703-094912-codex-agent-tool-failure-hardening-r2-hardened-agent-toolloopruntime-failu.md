---
name: "工具台反馈-20260703-094912-codex-agent-tool-failure-hardening-r2-Hardened Agent ToolLoopRuntime failu"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-tool-failure-hardening-r2"
created: "2026-07-03T09:49:12.411907+00:00"
---

# MCP 使用反馈

## 任务

Hardened Agent ToolLoopRuntime failure semantics so external/network tool failures retain structured hard-failure signals instead of looking like ordinary tool output.

## 顺畅度

- 评分：4/5
- 体感：Mostly smooth: brief/plan_task/codegraph plus lint/run_test/finish_task gave the needed trail, and recovery after the 502 was straightforward.

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, memory_search, lint, run_test, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task correctly reports all dirty files, but in a multi-agent dirty worktree it is hard to distinguish my touched files from unrelated pre-existing changes in the success boolean.

## 缺少的工具 / 能力

A first-class 'my changes since start' or 'diff ownership' helper would make boundary reporting cleaner in parallel sweep branches.

## 升级建议

Let finish_task accept an explicit expected_changed_paths list and report separate task-boundary status versus whole-worktree dirty status.

## 建议移除或合并的工具

无

## 其他备注

No commit/push. Task changes were limited to modules/agent; project memory/feedback were written through MCP.

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 960,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 573,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "code_explore",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 389,
    "error": 17,
    "avg_duration_seconds": 0.785
  },
  {
    "tool": "sql",
    "calls": 351,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 345,
    "error": 3,
    "avg_duration_seconds": 0.469
  },
  {
    "tool": "code_impact",
    "calls": 342,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 331,
    "error": 2,
    "avg_duration_seconds": 3.249
  },
  {
    "tool": "worktree_guard",
    "calls": 323,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 263,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
