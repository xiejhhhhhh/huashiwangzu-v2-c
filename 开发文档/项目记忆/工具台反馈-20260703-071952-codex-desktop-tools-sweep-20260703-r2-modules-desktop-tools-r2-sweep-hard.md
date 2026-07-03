---
name: "工具台反馈-20260703-071952-codex-desktop-tools-sweep-20260703-r2-modules/desktop-tools r2 sweep: hard"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-tools-sweep-20260703-r2"
created: "2026-07-03T07:19:52.954529+00:00"
---

# MCP 使用反馈

## 任务

modules/desktop-tools r2 sweep: hardened file/list/read bridge contracts, manifest metadata, and sandbox validation.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_node/code_impact/capabilities/probe 能快速定位 desktop-tools 的真实注册与活系统行为。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, probe, call_capability, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 对模块任务只允许 modules/{key}/，无法声明项目记忆为允许路径；共享分支多 worker dirty 时 success=false 容易掩盖本 worker 边界实际合规。

## 缺少的工具 / 能力

希望 finish_task 支持 allowed_prefixes 或 explicit memory_allowed=true，并区分 pre-existing dirty 与本次 agent touched files。

## 升级建议

worktree_guard/finish_task 可输出 since-start baseline 或 agent-owned changed files，方便并行 sweep 场景验收。

## 建议移除或合并的工具

无

## 其他备注

活测为避免留下框架文件测试数据，选择只读与坏参探针；create/delete/publish 未做破坏性活测。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 712,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 497,
    "error": 0,
    "avg_duration_seconds": 0.023
  },
  {
    "tool": "code_explore",
    "calls": 322,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 279,
    "error": 2,
    "avg_duration_seconds": 3.672
  },
  {
    "tool": "worktree_guard",
    "calls": 266,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 265,
    "error": 12,
    "avg_duration_seconds": 0.689
  },
  {
    "tool": "code_impact",
    "calls": 249,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 216,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 208,
    "error": 2,
    "avg_duration_seconds": 0.524
  }
]
```
