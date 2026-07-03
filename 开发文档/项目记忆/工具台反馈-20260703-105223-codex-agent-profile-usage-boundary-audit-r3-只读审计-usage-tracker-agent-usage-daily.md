---
name: "工具台反馈-20260703-105223-codex-agent-profile-usage-boundary-audit-r3-只读审计 usage_tracker/agent_usage_daily"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-profile-usage-boundary-audit-r3"
created: "2026-07-03T10:52:23.736906+00:00"
---

# MCP 使用反馈

## 任务

只读审计 usage_tracker/agent_usage_daily 边界与 Agent 画像治理链路断点。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_explore + SQL + 活系统探针能快速形成证据闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, routes, capabilities, db_schema, db_reverse_audit, sql, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

db_reverse_audit 的 table_filter 传逗号列表时返回 0 表，像是只支持单一子串过滤，容易误判。

## 缺少的工具 / 能力

希望 db_reverse_audit 支持多表精确列表或 SQL-like IN 过滤，并输出当前 worker handler 与任务队列类型的差异诊断。

## 升级建议

给 finish_task 增加 read-only audit 模式，允许只记录现有 dirty 与验证工具，不触发模块越界失败语义。

## 建议移除或合并的工具

无

## 其他备注

本次未改代码；memory_write 会按规则新增项目记忆。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1069,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 600,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 436,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 425,
    "error": 22,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 415,
    "error": 17,
    "avg_duration_seconds": 0.754
  },
  {
    "tool": "probe",
    "calls": 414,
    "error": 3,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "run_test",
    "calls": 376,
    "error": 2,
    "avg_duration_seconds": 3.153
  },
  {
    "tool": "code_impact",
    "calls": 372,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 356,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 304,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
