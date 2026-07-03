---
name: "工具台反馈-20260703-110242-codex-framework-gateway-usage-boundary-r3-修复框架 gateway usage_tracker 越界写 agent"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-framework-gateway-usage-boundary-r3"
created: "2026-07-03T11:02:42.303291+00:00"
---

# MCP 使用反馈

## 任务

修复框架 gateway usage_tracker 越界写 agent_usage_daily，改为 framework_gateway_usage_daily 并补 focused tests。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅：brief/plan/worktree/codegraph/db_schema/probe/finish_task 串起来能清楚定位边界问题和验证闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, db_reverse_audit, routes, probe, sql, tail_log, lint, run_test, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的 boundary_check 默认只查 forbidden，不能传 allowed_prefixes；需要额外手动 worktree_guard 才能表达本任务允许边界。另外并行脏改很多时，归因需要人工对照初始 guard。

## 缺少的工具 / 能力

希望 finish_task 支持 allowed_prefixes 参数并在报告里区分“本次初始已存在/运行中新增/当前 agent 已修改”的 dirty 来源。

## 升级建议

给 worktree_guard/finish_task 增加 start_snapshot_id 或 baseline 参数，会让多 agent 并行时的边界验收更稳。

## 建议移除或合并的工具

无

## 其他备注

工具台在 DB schema、反向审计和活探针组合上很有用；本次没有使用 quick_fix_patch，因为新增模型/测试更适合手工 apply_patch。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1100,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 612,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 444,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 440,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 436,
    "error": 5,
    "avg_duration_seconds": 0.447
  },
  {
    "tool": "call_capability",
    "calls": 420,
    "error": 17,
    "avg_duration_seconds": 0.748
  },
  {
    "tool": "run_test",
    "calls": 391,
    "error": 2,
    "avg_duration_seconds": 3.156
  },
  {
    "tool": "code_impact",
    "calls": 385,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 366,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 316,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
