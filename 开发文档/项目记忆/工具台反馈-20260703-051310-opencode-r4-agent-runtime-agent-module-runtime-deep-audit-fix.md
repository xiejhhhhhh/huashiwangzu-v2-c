---
name: "工具台反馈-20260703-051310-opencode-r4-agent-runtime-Agent module runtime deep audit: fix"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode-r4-agent-runtime"
created: "2026-07-03T05:13:10.588797+00:00"
---

# MCP 使用反馈

## 任务

Agent module runtime deep audit: fix P0 spawn_subagent double-wrapping, P1 memory_dream fake success, verify profile_evolve dirty diff

## 顺畅度

- 评分：4/5
- 体感：Smooth. CodeGraph + project toolkit MCP made code navigation efficient.

## 本次用到的工具

codegraph_explore, codegraph_node, brief, plan_task, worktree_guard, routes, capabilities, db_schema, lint, run_test, memory_write, finish_task

## 卡点 / 不顺手的地方

finish_task boundary check flagged pre-existing dirty files outside module as 'outside_allowed'. Rule 19 OK since my actual changes are within module. Minor confusion.

## 缺少的工具 / 能力

无

## 升级建议

无

## 建议移除或合并的工具

无

## 其他备注

This audit session was focused — 2 concrete bugs found and fixed, 1 pre-existing dirty diff verified. CodeGraph saved significant reading time.

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 330,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 234,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 177,
    "error": 1,
    "avg_duration_seconds": 2.724
  },
  {
    "tool": "worktree_guard",
    "calls": 174,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 162,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "code_impact",
    "calls": 147,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "probe",
    "calls": 127,
    "error": 0,
    "avg_duration_seconds": 0.482
  },
  {
    "tool": "plan_task",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
