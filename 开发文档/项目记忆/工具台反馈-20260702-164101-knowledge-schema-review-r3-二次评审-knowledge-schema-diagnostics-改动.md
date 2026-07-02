---
name: "工具台反馈-20260702-164101-knowledge-schema-review-r3-二次评审 knowledge schema/diagnostics 改动"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "knowledge-schema-review-r3"
created: "2026-07-02T16:41:01.719387+00:00"
---

# MCP 使用反馈

## 任务

二次评审 knowledge schema/diagnostics 改动，确认诊断账本独立事务与 pipeline 主链路无重复流程，并小修 raw_collection 单测漂移。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/code_node/db_schema/run_test/lint 串起来很省心。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, db_schema, tail_log, run_test, lint, finish_task, memory_write

## 卡点 / 不顺手的地方

lint 工具一次只能接单文件，传多个路径会被当作一个不存在的文件；finish_task 因全局其它 agent dirty 变更返回 success=false，但这对模块复核结论需要人工解释。

## 缺少的工具 / 能力

希望 lint 支持路径列表；希望 worktree_guard/finish_task 支持声明“本 agent 本次新增改动范围”以区分既有脏工作区。

## 升级建议

finish_task 可在全局 dirty 越界时额外给出 allowed prefix 内 diff 摘要和 forbidden 命中优先级，减少噪音。

## 建议移除或合并的工具

无

## 其他备注

本次实际编辑仅 modules/knowledge/tests/test_raw_collection.py；未改生产代码。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 364,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 264,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 178,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "sql",
    "calls": 170,
    "error": 7,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 113,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "db_schema",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "run_test",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 2.394
  },
  {
    "tool": "probe",
    "calls": 85,
    "error": 0,
    "avg_duration_seconds": 0.568
  },
  {
    "tool": "plan_task",
    "calls": 79,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
