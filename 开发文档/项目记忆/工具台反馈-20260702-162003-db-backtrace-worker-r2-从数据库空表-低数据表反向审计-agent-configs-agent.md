---
name: "工具台反馈-20260702-162003-db-backtrace-worker-r2-从数据库空表/低数据表反向审计 agent_configs、agent_"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "db-backtrace-worker-r2"
created: "2026-07-02T16:20:03.387352+00:00"
---

# MCP 使用反馈

## 任务

从数据库空表/低数据表反向审计 agent_configs、agent_skill_usage、memory_experiences、memory_links、imagegen_records、codemap_feedback；确认多数为空属于未触发/人工反馈状态，并修复 memory post-save embedding SQL 断链。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_reverse_audit 很适合从表反推 owner 和下一步探针。

## 本次用到的工具

brief, plan_task, worktree_guard, db_reverse_audit, db_schema, capabilities, routes, code_explore, tail_log, probe, call_capability, lint, run_test, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 混合 backend 测试目标和模块 sandbox 绝对路径时归一化失败；CodeGraph 对 tool_discovery.record_skill_usage 的调用关系初次没命中，需要 rg 补证。

## 缺少的工具 / 能力

希望 db_reverse_audit 能直接带出“表为空但最近日志有同表链路错误”的聚合视图。

## 升级建议

finish_task 支持混合 repo 根路径、backend/tests 路径和 modules/*/sandbox 路径；code_explore/CodeGraph 对动态服务函数调用可增强。

## 建议移除或合并的工具

无

## 其他备注

并行 agent 期间工作区出现大量非本任务 dirty 文件，本次未触碰也未回退。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 321,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 237,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 166,
    "error": 0,
    "avg_duration_seconds": 0.309
  },
  {
    "tool": "sql",
    "calls": 164,
    "error": 7,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 103,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "worktree_guard",
    "calls": 101,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 89,
    "error": 0,
    "avg_duration_seconds": 2.695
  },
  {
    "tool": "db_schema",
    "calls": 88,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 77,
    "error": 0,
    "avg_duration_seconds": 0.521
  },
  {
    "tool": "plan_task",
    "calls": 71,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
