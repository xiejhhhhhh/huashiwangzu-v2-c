---
name: "工具台反馈-20260703-071455-codex-web-tools-sweep-20260703-r2-modules/web-tools r2 sweep: hardened"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-web-tools-sweep-20260703-r2"
created: "2026-07-03T07:14:55.362617+00:00"
---

# MCP 使用反馈

## 任务

modules/web-tools r2 sweep: hardened fetch streaming limit, URL/input/output contracts, fake failure semantics, and sandbox contract tests.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/code_explore/routes/capabilities/lint/run_test/probe/call_capability 串起来足够完成模块 sweep。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, routes, capabilities, db_schema, lint, run_test, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的边界检查只能按当前全仓 dirty 判断，多个并行 worker 时会把他人改动和 data/uploads 一并标成 outside_allowed，需要人工解释。

## 缺少的工具 / 能力

希望有按本次 touched files 或 git diff pathspec 的 finish/boundary 模式，能在并行 sweep 分支里区分本 worker 改动和其它 dirty。

## 升级建议

finish_task 可接受 allowed_prefixes，并在报告里单独输出 `git diff --name-only -- <module>` 的模块内改动清单。

## 建议移除或合并的工具

无

## 其他备注

活栈后端由 watchdog/多 worker 自动重新监听 33000；首次手动 uvicorn 因端口已有监听退出，但探针确认新代码已加载。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 708,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 491,
    "error": 0,
    "avg_duration_seconds": 0.023
  },
  {
    "tool": "code_explore",
    "calls": 321,
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
    "calls": 277,
    "error": 2,
    "avg_duration_seconds": 3.693
  },
  {
    "tool": "worktree_guard",
    "calls": 260,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 257,
    "error": 12,
    "avg_duration_seconds": 0.671
  },
  {
    "tool": "code_impact",
    "calls": 247,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 214,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 205,
    "error": 2,
    "avg_duration_seconds": 0.527
  }
]
```
