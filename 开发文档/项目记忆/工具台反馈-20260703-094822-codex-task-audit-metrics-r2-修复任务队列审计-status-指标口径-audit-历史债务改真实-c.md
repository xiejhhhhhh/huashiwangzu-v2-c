---
name: "工具台反馈-20260703-094822-codex-task-audit-metrics-r2-修复任务队列审计/status 指标口径：audit 历史债务改真实 c"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-task-audit-metrics-r2"
created: "2026-07-03T09:48:22.459711+00:00"
---

# MCP 使用反馈

## 任务

修复任务队列审计/status 指标口径：audit 历史债务改真实 count，worker status 等待时长排除未来 scheduled pending，并补回归测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/lint/run_test/probe/finish_task 都覆盖了本次闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 能发现越界脏改，但 finish_task 默认未带 allowed_prefixes，收工报告只能看到全局 dirty，不能直接区分本 agent 改动与其他 agent 改动。另 scripts/start_backend.sh 无执行位，需要用 zsh 调用。

## 缺少的工具 / 能力

无

## 升级建议

finish_task 若支持 allowed_prefixes 参数并在报告中单列 outside_allowed，会更适合并行 agent 场景。start_backend 脚本可考虑补执行位或工具台提供 restart_backend。

## 建议移除或合并的工具

无

## 其他备注

活系统最初仍运行旧代码，重启/恢复 watchdog 后 probe 证实新指标生效。

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
    "calls": 573,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "code_explore",
    "calls": 391,
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
    "tool": "probe",
    "calls": 345,
    "error": 3,
    "avg_duration_seconds": 0.469
  },
  {
    "tool": "code_impact",
    "calls": 342,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 331,
    "error": 2,
    "avg_duration_seconds": 3.249
  },
  {
    "tool": "worktree_guard",
    "calls": 323,
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
