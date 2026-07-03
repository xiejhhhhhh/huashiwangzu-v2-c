---
name: "工具台反馈-20260703-080751-codex-media-asr-sweep-20260703-r2-modules/media-asr r2 sweep: hardened"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-media-asr-sweep-20260703-r2"
created: "2026-07-03T08:07:51.196868+00:00"
---

# MCP 使用反馈

## 任务

modules/media-asr r2 sweep: hardened parameter validation, local ffprobe media boundary, Whisper model whitelist, manifest docs, and production-code sandbox tests.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；brief/plan_task/code_node/lint/run_test/probe/call_capability 串起来能覆盖模块扫雷闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task/worktree_guard 在并行多 agent dirty 场景下只能按全仓判 false，无法表达“本 agent 改动合规但其他 agent 改动存在”的分层状态。

## 缺少的工具 / 能力

希望有按 agent/allowed_extra_prefixes 的 finish_task 边界汇总，允许 modules/{module}/ + 当前 agent 项目记忆，同时把其他 dirty 标为外部基线而非失败。

## 升级建议

finish_task 可增加 baseline_dirty 参数或 since-start snapshot，对并行扫雷任务输出 own_changed/outside_baseline/new_outside 三段。

## 建议移除或合并的工具

无

## 其他备注

call_capability 负例探针对确认 live path 很有用；capabilities 工具能从 manifest 读到新描述，无需重启。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 865,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 554,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "call_capability",
    "calls": 360,
    "error": 17,
    "avg_duration_seconds": 0.745
  },
  {
    "tool": "code_explore",
    "calls": 355,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 321,
    "error": 3,
    "avg_duration_seconds": 0.474
  },
  {
    "tool": "run_test",
    "calls": 311,
    "error": 2,
    "avg_duration_seconds": 3.405
  },
  {
    "tool": "code_impact",
    "calls": 310,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "sql",
    "calls": 309,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 302,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
