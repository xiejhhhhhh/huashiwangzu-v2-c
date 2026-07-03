---
name: "工具台反馈-20260703-094614-codex-browser-tools-network-hardening-r2-修复 browser-tools timeout 无上限和直链 HTTP"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-browser-tools-network-hardening-r2"
created: "2026-07-03T09:46:14.923891+00:00"
---

# MCP 使用反馈

## 任务

修复 browser-tools timeout 无上限和直链 HTTP 下载全量读入问题

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/finish_task 给出了足够证据和验收框架。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 会把其他 agent 的既有脏文件计入当前模块边界失败，需要人工在最终报告中区分本任务 diff 与全仓 dirty。

## 缺少的工具 / 能力

无

## 升级建议

finish_task 可以额外输出本次指定 allowed path 的 diff-only 通过状态，和全仓 dirty 状态并列展示，减少多 agent 并行时的歧义。

## 建议移除或合并的工具

无

## 其他备注

未 commit/push；本任务落盘范围为 modules/browser-tools 两个文件，加本条项目记忆/反馈。

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
    "calls": 572,
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
    "calls": 389,
    "error": 17,
    "avg_duration_seconds": 0.785
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
    "calls": 340,
    "error": 3,
    "avg_duration_seconds": 0.464
  },
  {
    "tool": "run_test",
    "calls": 327,
    "error": 2,
    "avg_duration_seconds": 3.281
  },
  {
    "tool": "worktree_guard",
    "calls": 322,
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
