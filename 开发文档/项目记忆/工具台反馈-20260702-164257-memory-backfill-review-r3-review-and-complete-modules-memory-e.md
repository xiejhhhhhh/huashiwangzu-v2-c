---
name: "工具台反馈-20260702-164257-memory-backfill-review-r3-Review and complete modules/memory e"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "memory-backfill-review-r3"
created: "2026-07-02T16:42:57.136579+00:00"
---

# MCP 使用反馈

## 任务

Review and complete modules/memory embedding backfill governance chain after interrupted agent work.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；brief/plan_task/code_node/capabilities/call_capability 对接手脏工作区很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, memory_search, lint, run_test, call_capability, probe, sql, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 在脏工作区正确报边界失败，但混合传入 modules/ 和 backend/tests 测试目标时路径归一化出了错；lint_paths 也不支持空格分隔多个路径。

## 缺少的工具 / 能力

希望 finish_task 支持声明 known pre-existing outside changes 或只校验本次 agent touched files；也希望提供 backend restart/status 工具，避免手写 lsof/kill。

## 升级建议

finish_task 的 test_targets 可复用 run_test 的多目标归一化逻辑，lint_paths 可支持换行/逗号多个路径；worktree_guard 若能显示 since-start baseline 会更适合多人并行接力。

## 建议移除或合并的工具

无

## 其他备注

活系统第一次 call_capability 返回 404 是旧后端未加载未提交 router 注册；重启后验证通过。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 369,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 264,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "sql",
    "calls": 171,
    "error": 7,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 112,
    "error": 0,
    "avg_duration_seconds": 2.31
  },
  {
    "tool": "db_schema",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 86,
    "error": 0,
    "avg_duration_seconds": 0.566
  },
  {
    "tool": "plan_task",
    "calls": 79,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
