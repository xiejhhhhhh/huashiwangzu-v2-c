---
name: "工具台反馈-20260703-110243-codex-agent-bootstrap-handler-registration-r3-修复 Agent 后台 handler 注册断路，使 RuntimeTa"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-bootstrap-handler-registration-r3"
created: "2026-07-03T11:02:43.791416+00:00"
---

# MCP 使用反馈

## 任务

修复 Agent 后台 handler 注册断路，使 RuntimeTaskSink 入队任务在活栈 worker registry 中可见并被消费。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/code_explore/probe/run_test 覆盖了从断点定位到活栈验证的闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, tail_log, lint, run_test, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 会按当前整个 worktree 判边界，遇到并行 agent/其他会话改动时会显示失败；需要人工区分本任务 diff 与并行 diff。

## 缺少的工具 / 能力

缺少一个按“本会话触碰文件”或显式 path list 做边界判定的 finish_task 模式；也缺少任务队列测试任务的一键 submit/poll/cleanup 工具。

## 升级建议

finish_task 支持 changed_files_allowlist 或 baseline token（开工 worktree_guard 快照）会更适合多 agent 并行。probe 可以增加 JSONPath 断言，直接验证 health worker handlers 包含指定集合。

## 建议移除或合并的工具

无

## 其他备注

本次没有改框架 loader，因为证据显示 manifest loader 已正常 import router，断点在 agent router 未调用 register_agent_tasks。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1100,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 612,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 444,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 440,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 436,
    "error": 5,
    "avg_duration_seconds": 0.447
  },
  {
    "tool": "call_capability",
    "calls": 420,
    "error": 17,
    "avg_duration_seconds": 0.748
  },
  {
    "tool": "run_test",
    "calls": 391,
    "error": 2,
    "avg_duration_seconds": 3.156
  },
  {
    "tool": "code_impact",
    "calls": 385,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 366,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 316,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
