---
name: "工具台反馈-20260703-051340-opencode-r3-knowledge-memory-Deep audit knowledge + memory data c"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode-r3-knowledge-memory"
created: "2026-07-03T05:13:40.136178+00:00"
---

# MCP 使用反馈

## 任务

Deep audit knowledge + memory data chain: found & fixed 3 additional gaps, verified existing dirty fixes, 75 tests green

## 顺畅度

- 评分：4/5
- 体感：顺畅。CodeGraph探索非常高效，测试秒级返回。

## 本次用到的工具

code_explore, code_node, db_schema, db_reverse_audit, plan_task, worktree_guard, lint, run_test, memory_write, finish_task

## 卡点 / 不顺手的地方

finish_task边界检查将memory模块文件标为"outside_allowed"因为module_key设的是knowledge，但实际任务覆盖两个模块，建议支持逗号分隔多模块。

## 缺少的工具 / 能力

无

## 升级建议

no

## 建议移除或合并的工具

无

## 其他备注

无

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
    "calls": 178,
    "error": 1,
    "avg_duration_seconds": 2.716
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
