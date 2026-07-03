---
name: "工具台反馈-20260703-094247-codex-scheduler-old-payload-guard-r2-修复 scheduler 旧空 payload 到点假成功问题，并补 s"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-scheduler-old-payload-guard-r2"
created: "2026-07-03T09:42:47.372616+00:00"
---

# MCP 使用反馈

## 任务

修复 scheduler 旧空 payload 到点假成功问题，并补 sandbox 覆盖。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅：brief、plan_task、CodeGraph、lint/run_test/probe/call_capability 都能覆盖这个小修复闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 会把其他 agent 的并发修改一起标红，需要人工区分本次 diff 与全局 dirty；本次按不回退原则处理。

## 缺少的工具 / 能力

无

## 升级建议

finish_task 若能额外展示“本 agent 本轮新增/修改文件”和“既有/并发 dirty 文件”分组，会更适合并行 sweep 场景。

## 建议移除或合并的工具

无

## 其他备注

未做 DB 清理、未 commit/push，符合任务约束。

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
    "calls": 570,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "code_explore",
    "calls": 390,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 388,
    "error": 17,
    "avg_duration_seconds": 0.786
  },
  {
    "tool": "sql",
    "calls": 351,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 341,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "probe",
    "calls": 337,
    "error": 3,
    "avg_duration_seconds": 0.465
  },
  {
    "tool": "run_test",
    "calls": 325,
    "error": 2,
    "avg_duration_seconds": 3.296
  },
  {
    "tool": "worktree_guard",
    "calls": 320,
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
