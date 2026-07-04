---
name: "工具台反馈-20260704-134055-codex-Knowledge / Content IR / Agent evide"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-04T13:40:55.896153+00:00"
---

# MCP 使用反馈

## 任务

Knowledge / Content IR / Agent evidence / Artifact 权威归一收口，补后端权威字段、artifact publish 标准回包、Agent/Knowledge 前端证据展示、文档与验收记录。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，finish_task 能清楚暴露 dirty 规模和 release 风险，适合全局任务收口。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore/code_node/code_impact, capabilities, db_schema, routes, probe, release_gate, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

工作区并行任务 dirty 很多，finish_task 未带开工 baseline 时会把全部文件标为 new_since_baseline，收工归因噪声较大。

## 缺少的工具 / 能力

希望工具台支持从本次执行上下文自动继承开工 worktree_guard baseline，或允许按核心 touched paths 生成简洁交付视图。

## 升级建议

finish_task 可增加 `reported_paths` 字段，用于展示本轮归因文件，同时保留完整 dirty 风险列表。

## 建议移除或合并的工具

无

## 其他备注

本次仍按要求完成 memory_write 和 mcp_feedback；未提交 commit。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 453,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "code_explore",
    "calls": 281,
    "error": 0,
    "avg_duration_seconds": 0.341
  },
  {
    "tool": "worktree_guard",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 169,
    "error": 4,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "brief",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.765
  },
  {
    "tool": "plan_task",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "code_impact",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "call_capability",
    "calls": 119,
    "error": 5,
    "avg_duration_seconds": 0.297
  },
  {
    "tool": "sql",
    "calls": 116,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "routes",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.051
  }
]
```
