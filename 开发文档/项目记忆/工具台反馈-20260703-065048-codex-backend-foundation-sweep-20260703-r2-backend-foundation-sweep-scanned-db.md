---
name: "工具台反馈-20260703-065048-codex-backend-foundation-sweep-20260703-r2-Backend foundation sweep: scanned DB"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-backend-foundation-sweep-20260703-r2"
created: "2026-07-03T06:50:48.786201+00:00"
---

# MCP 使用反馈

## 任务

Backend foundation sweep: scanned DB/health/task/file/content/module-registry chains and fixed module call false-success, content export file access, export overwrite SQL filtering, and sent share deleted-file filtering.

## 顺畅度

- 评分：4/5
- 体感：Mostly smooth: brief/plan/codegraph/routes/db audit/probe/finish_task gave a good evidence trail and fast verification loop.

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, db_schema, db_reverse_audit, sql, probe, lint, run_test, tail_log, _restart_backend, finish_task, memory_write, mcp_feedback, agent_board_claim, agent_board_heartbeat

## 卡点 / 不顺手的地方

worktree_guard correctly exposed unrelated parallel-agent changes, but finish_task boundary mode for global framework tasks did not let me pass allowed_prefixes, so it reported all dirty files as in-scope sample rather than distinguishing my diff cleanly.

## 缺少的工具 / 能力

A finish_task allowed_prefixes parameter or a 'my_changed_paths' field would make multi-agent dirty worktrees easier to report without ambiguity.

## 升级建议

Add an optional probe mode that can run against in-process ASGI before restart and label live-server code freshness, because pre-restart probes can show old behavior after code edits.

## 建议移除或合并的工具

无

## 其他备注

Ruff/tooling worked well. db_reverse_audit output was long/truncated for 80 tables; a compact framework-only summary mode would be useful.

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 657,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 462,
    "error": 0,
    "avg_duration_seconds": 0.021
  },
  {
    "tool": "code_explore",
    "calls": 308,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 290,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 243,
    "error": 2,
    "avg_duration_seconds": 3.572
  },
  {
    "tool": "worktree_guard",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 232,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 200,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "call_capability",
    "calls": 182,
    "error": 12,
    "avg_duration_seconds": 0.708
  },
  {
    "tool": "probe",
    "calls": 181,
    "error": 2,
    "avg_duration_seconds": 0.454
  }
]
```
