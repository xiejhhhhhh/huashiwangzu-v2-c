---
name: "工具台反馈-20260703-093532-codex-flow-audit-tasks-r2-只读审计任务队列、scheduler、后台 worker、多 worke"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-flow-audit-tasks-r2"
created: "2026-07-03T09:35:32.182953+00:00"
---

# MCP 使用反馈

## 任务

只读审计任务队列、scheduler、后台 worker、多 worker 状态流程问题

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph + DB 工具能很快把代码路径和真实队列水位对上。

## 本次用到的工具

brief, plan_task, worktree_guard, db_reverse_audit, db_schema, routes, capabilities, code_explore, code_node, tail_log, sql, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的 dirty 汇总与开工 baseline 不一致，可能受并行 agent 影响；sql 输出遇到长 JSON/换行时列展示会被切得较碎。

## 缺少的工具 / 能力

缺少一个只读的 worker/process aggregate 工具，能一次返回 uvicorn worker pid、每个 worker health/last_active/handler registry 与 DB 水位对照。

## 升级建议

db_reverse_audit 可以对 task 队列表内置状态分布、stale/future scheduled、semantic completed 规则，减少手写 SQL；sql 工具建议支持 named columns 输出或 CSV-safe JSON。

## 建议移除或合并的工具

无。

## 其他备注

本次未改代码未 commit；只写项目记忆和 MCP 反馈。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 940,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 567,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "call_capability",
    "calls": 387,
    "error": 17,
    "avg_duration_seconds": 0.788
  },
  {
    "tool": "code_explore",
    "calls": 381,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 344,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 335,
    "error": 3,
    "avg_duration_seconds": 0.466
  },
  {
    "tool": "code_impact",
    "calls": 331,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 322,
    "error": 2,
    "avg_duration_seconds": 3.316
  },
  {
    "tool": "worktree_guard",
    "calls": 314,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 258,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
