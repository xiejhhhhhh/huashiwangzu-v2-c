---
name: "工具台反馈-20260703-182713-codex-module-audit-conductor-模块专项维修五包并发收敛"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-module-audit-conductor"
created: "2026-07-03T18:27:13.933653+00:00"
---

# MCP 使用反馈

## 任务

模块专项维修五包并发收敛

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/codegraph/job 工具能支撑多子代理收敛。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, capabilities, tool_job_submit, tool_job_status, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 对并行任务中新出现的非本任务 dirty 只能标红，仍需人工解释基线与并行来源。

## 缺少的工具 / 能力

缺少按时间/agent 归因 dirty 文件的自动区分工具。

## 升级建议

finish_task 可支持追加 acknowledged paths 或基线快照续传，避免并行会话新增文件误判当前任务越界。

## 建议移除或合并的工具

无

## 其他备注

本轮使用 multi_agent 子代理并发执行 A-E 包，最终由主会话统一验收。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1302,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "lint",
    "calls": 654,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 573,
    "error": 8,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 556,
    "error": 0,
    "avg_duration_seconds": 0.326
  },
  {
    "tool": "call_capability",
    "calls": 499,
    "error": 17,
    "avg_duration_seconds": 0.681
  },
  {
    "tool": "run_test",
    "calls": 466,
    "error": 3,
    "avg_duration_seconds": 4.454
  },
  {
    "tool": "worktree_guard",
    "calls": 458,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 449,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 370,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
