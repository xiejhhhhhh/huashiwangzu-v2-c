---
name: "工具台反馈-20260703-105150-codex-framework-task-queue-knowledge-debt-audit-r3-只读审计 task_queue failed/pending 与 kno"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-framework-task-queue-knowledge-debt-audit-r3"
created: "2026-07-03T10:51:50.470425+00:00"
---

# MCP 使用反馈

## 任务

只读审计 task_queue failed/pending 与 knowledge pipeline/stale 历史债，从 DB、HTTP 活系统、CodeGraph 和日志倒推链路并落 memory_write。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，SQL/probe/CodeGraph 组合足够完成 DB 到代码链路倒推。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, routes, capabilities, db_schema, db_reverse_audit, probe, call_capability, tail_log, sql, memory_write, agent_board_claim, agent_board_heartbeat

## 卡点 / 不顺手的地方

probe/call_capability 大响应没有摘要模式，knowledge pipeline dry-run/dashboard 返回超大 items，容易淹没有效证据；sql 返回列名是 col0/col1，长查询复核时需要手动对照。

## 缺少的工具 / 能力

建议增加 task_queue_audit_summary/knowledge_debt_summary 这类只返回聚合和样本上限的工具；增加只读 SQL 输出保留字段别名的模式。

## 升级建议

给 probe 增加 response_path/filter/max_items 参数；给 sql 增加 named-columns JSON 输出；给 db_reverse_audit 可选 lifecycle join templates，例如 kb_documents→framework_file_items→task_queue。

## 建议移除或合并的工具

无

## 其他备注

任务板 heartbeat 可用；memory_write 已落 开发文档/项目记忆/p0-task-queue-and-knowledge-pipeline-debt-readonly-audit-r3.md。

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
    "calls": 423,
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
    "calls": 355,
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
