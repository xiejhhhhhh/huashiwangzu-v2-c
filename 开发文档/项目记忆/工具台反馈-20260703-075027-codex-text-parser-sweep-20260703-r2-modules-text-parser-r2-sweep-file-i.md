---
name: "工具台反馈-20260703-075027-codex-text-parser-sweep-20260703-r2-modules/text-parser r2 sweep: file_i"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-text-parser-sweep-20260703-r2"
created: "2026-07-03T07:50:27.312821+00:00"
---

# MCP 使用反馈

## 任务

modules/text-parser r2 sweep: file_id path verified via shared runner, parser core split, ValidationError conversion, truncation metadata, sandbox pytest coverage, README verification updated.

## 顺畅度

- 评分：4/5
- 体感：总体顺畅，codegraph 和工具台快速确认了路由/能力/影响面。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 会因并行 agent 的既有 data/uploads/其他模块改动整体标红，需要人工区分本任务新增改动；call_capability 命中常驻后端旧注册函数时没有提示可能需要重启。

## 缺少的工具 / 能力

希望有一个按 start-baseline 过滤的 worktree_guard，或能只报告当前 agent 写入后的新增越界。

## 升级建议

call_capability 可返回模块代码加载时间/进程启动时间，帮助判断探针失败是代码问题还是常驻服务未重启。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 784,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 526,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 339,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 322,
    "error": 17,
    "avg_duration_seconds": 0.714
  },
  {
    "tool": "sql",
    "calls": 304,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 296,
    "error": 2,
    "avg_duration_seconds": 3.545
  },
  {
    "tool": "worktree_guard",
    "calls": 290,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 281,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 277,
    "error": 2,
    "avg_duration_seconds": 0.486
  },
  {
    "tool": "db_schema",
    "calls": 230,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
