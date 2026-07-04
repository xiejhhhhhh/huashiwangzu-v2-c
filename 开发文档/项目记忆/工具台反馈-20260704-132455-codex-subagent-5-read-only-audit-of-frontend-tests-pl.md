---
name: "工具台反馈-20260704-132455-codex-subagent-5-Read-only audit of frontend/tests Pl"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-subagent-5"
created: "2026-07-04T13:24:55.592118+00:00"
---

# MCP 使用反馈

## 任务

Read-only audit of frontend/tests Playwright failure-state coverage for LoadState/ApiErrorInfo/notification error copy/jump.

## 顺畅度

- 评分：4/5
- 体感：Mostly smooth: brief/plan/guard/codegraph gave the needed map quickly.

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task cannot distinguish concurrent dirty changes from this read-only agent without a baseline JSON passed back into closeout.

## 缺少的工具 / 能力

A frontend-test coverage helper that maps TS/Vue symbols to Playwright/spec assertions would speed audits.

## 升级建议

Let finish_task accept the earlier worktree_guard result automatically within the same MCP session to avoid reporting concurrent changes as new_since_baseline.

## 建议移除或合并的工具

无

## 其他备注

No code edits were made; only mandatory project memory/feedback records were written.

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 421,
    "error": 0,
    "avg_duration_seconds": 0.148
  },
  {
    "tool": "code_explore",
    "calls": 273,
    "error": 0,
    "avg_duration_seconds": 0.341
  },
  {
    "tool": "worktree_guard",
    "calls": 176,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 168,
    "error": 4,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "brief",
    "calls": 133,
    "error": 0,
    "avg_duration_seconds": 0.764
  },
  {
    "tool": "plan_task",
    "calls": 133,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "code_impact",
    "calls": 115,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 115,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 114,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "routes",
    "calls": 92,
    "error": 0,
    "avg_duration_seconds": 0.052
  }
]
```
