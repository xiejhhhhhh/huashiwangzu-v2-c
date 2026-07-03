---
name: "工具台反馈-20260703-071732-codex-github-search-sweep-20260703-r2-modules/github-search r2 sweep: hard"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-github-search-sweep-20260703-r2"
created: "2026-07-03T07:17:32.625985+00:00"
---

# MCP 使用反馈

## 任务

modules/github-search r2 sweep: harden GitHub CLI search/cache/rate-limit/error semantics, align manifest, and replace sandbox with offline contract tests.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/capabilities/lint/run_test/call_capability 串起来能完成模块级扫雷。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task/worktree_guard 在多 worker 共享脏工作区下只能给全仓失败，虽然本 worker 的 scoped diff 是干净的；需要人工解读 outside_allowed。

## 缺少的工具 / 能力

缺少 scoped_finish_task 或 scoped_boundary_guard：只按指定 allowed_prefixes 判定本 worker 是否合规，同时把其他脏文件作为背景信息而非失败。

## 升级建议

finish_task 增加 allowed_prefixes 参数并输出 scoped_success；call_capability 可选提示服务代码时间戳/进程是否加载当前磁盘版本，避免常驻后端未重启时误判新代码活测。

## 建议移除或合并的工具

无

## 其他备注

本次未重启常驻后端，避免把其他 worker 的大量未提交改动一起加载；新错误语义通过 sandbox 导入新 router 验证，真实 GitHub 能力通过现有活栈验证。

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
    "calls": 494,
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
    "calls": 263,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 261,
    "error": 12,
    "avg_duration_seconds": 0.696
  },
  {
    "tool": "code_impact",
    "calls": 248,
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
    "calls": 207,
    "error": 2,
    "avg_duration_seconds": 0.525
  }
]
```
