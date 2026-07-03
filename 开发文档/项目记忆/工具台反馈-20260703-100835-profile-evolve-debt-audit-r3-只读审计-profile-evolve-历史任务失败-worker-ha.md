---
name: "工具台反馈-20260703-100835-profile-evolve-debt-audit-r3-只读审计 profile_evolve 历史任务失败、worker ha"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "profile-evolve-debt-audit-r3"
created: "2026-07-03T10:08:35.760627+00:00"
---

# MCP 使用反馈

## 任务

只读审计 profile_evolve 历史任务失败、worker handler/import/JSON 假成功假失败链路。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和任务审计接口能很快定位 profile_evolve 与 worker 语义链路。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, tail_log, routes, probe, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

缺少只读 SQL MCP 工具；为了查 completed result 语义假成功，只能用后端 Python/SQLAlchemy driver 级只读查询。finish_task 看到并发脏文件较多，容易和本只读审计混淆。

## 缺少的工具 / 能力

建议补一个 read_only_sql 或 task_queue_query 工具，支持按 task_type/status/error/result 时间窗查聚合与样本。

## 升级建议

task_queue_audit 可以直接暴露 completed semantic-failure 历史窗口，不只 24h 健康指标；governance dry-run 可支持 task_type filter。

## 建议移除或合并的工具

无

## 其他备注

本次未改代码/数据/提交；memory_write 和 mcp_feedback 是按任务要求写入项目记忆。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1014,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 583,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 407,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 393,
    "error": 17,
    "avg_duration_seconds": 0.78
  },
  {
    "tool": "probe",
    "calls": 368,
    "error": 3,
    "avg_duration_seconds": 0.457
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 357,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 345,
    "error": 2,
    "avg_duration_seconds": 3.206
  },
  {
    "tool": "worktree_guard",
    "calls": 333,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 283,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
