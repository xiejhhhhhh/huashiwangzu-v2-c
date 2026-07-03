---
name: "工具台反馈-20260703-101821-agent-profile-registration-cleanup-r3-清理 agent profile_evolve handler 重复注册"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "agent-profile-registration-cleanup-r3"
created: "2026-07-03T10:18:21.712961+00:00"
---

# MCP 使用反馈

## 任务

清理 agent profile_evolve handler 重复注册路径，统一由 bootstrap.register_agent_tasks 注册后台任务 handler。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；brief/plan_task/CodeGraph/finish_task 能快速定位重复注册和验证路径。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

共享工作区已有其他代理 dirty 项时，worktree_guard 和 finish_task 会整体 success=false，需人工区分本任务改动与既有现场。

## 缺少的工具 / 能力

无

## 升级建议

finish_task 可支持传入本任务 allowed_prefixes 或 baseline dirty snapshot，用于在共享工作树中区分“本任务新增越界”和“既有越界”。

## 建议移除或合并的工具

无

## 其他备注

未 commit/push；未触碰 backend/content 或 modules/knowledge。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1027,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 594,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 417,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 396,
    "error": 17,
    "avg_duration_seconds": 0.776
  },
  {
    "tool": "probe",
    "calls": 376,
    "error": 3,
    "avg_duration_seconds": 0.452
  },
  {
    "tool": "code_impact",
    "calls": 367,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 366,
    "error": 2,
    "avg_duration_seconds": 3.196
  },
  {
    "tool": "worktree_guard",
    "calls": 343,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 286,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
