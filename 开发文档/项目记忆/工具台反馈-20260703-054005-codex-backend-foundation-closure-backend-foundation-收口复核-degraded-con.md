---
name: "工具台反馈-20260703-054005-codex-backend-foundation-closure-backend foundation 收口复核：degraded Con"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-backend-foundation-closure"
created: "2026-07-03T05:40:05.950665+00:00"
---

# MCP 使用反馈

## 任务

backend foundation 收口复核：degraded ContentPackage 消费链路与 private module capability 回滚/清理测试补强。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/finish_task 串起来很省时间。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

lint 工具一次只接受单文件，传多路径时报“文件不存在”；finish_task 输出很长但有用。

## 缺少的工具 / 能力

无。

## 升级建议

lint 可以支持换行分隔多文件，或像 finish_task 一样批量执行并分别汇总。

## 建议移除或合并的工具

无。

## 其他备注

本轮目标工作树已有大量并行 worker dirty 文件，工具台 boundary/finish_task 对说明风险很有帮助。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 466,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 358,
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
    "calls": 259,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "worktree_guard",
    "calls": 198,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 192,
    "error": 2,
    "avg_duration_seconds": 3.174
  },
  {
    "tool": "db_schema",
    "calls": 163,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "code_impact",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "plan_task",
    "calls": 140,
    "error": 0,
    "avg_duration_seconds": 0.007
  },
  {
    "tool": "probe",
    "calls": 135,
    "error": 0,
    "avg_duration_seconds": 0.471
  }
]
```
