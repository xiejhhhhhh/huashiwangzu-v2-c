---
name: "工具台反馈-20260703-193336-codex-db-reverse-audit-数据库反向链路只读审计，从 125 张表反推后端、capability、"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-db-reverse-audit"
created: "2026-07-03T19:33:36.424904+00:00"
---

# MCP 使用反馈

## 任务

数据库反向链路只读审计，从 125 张表反推后端、capability、前端、用户行为和测试覆盖，产出审计报告。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_schema 和 db_reverse_audit 对快速定位表族、空表和代码引用很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, db_schema, db_reverse_audit, routes, capabilities, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

db_reverse_audit 输出 125 表时内容过长被截断，需要再用 psql 手工补全行数、状态分布和 owner 分布。

## 缺少的工具 / 能力

希望有一个 read-only db_table_stats 工具，可一次输出全表 count、关键字段、status distinct、owner/user 分布、时间范围，并支持 Markdown/JSON 压缩输出。

## 升级建议

给 db_reverse_audit 增加分组摘要和分页/cursor；给 finish_task 支持标记“非本轮已有未跟踪文件”，避免和本轮新增文档混在一起。

## 建议移除或合并的工具

无

## 其他备注

本轮遵守只读数据库和不改代码，只写用户指定报告以及项目规则要求的记忆/反馈。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1378,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 664,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 610,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "probe",
    "calls": 578,
    "error": 8,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "sql",
    "calls": 578,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 499,
    "error": 17,
    "avg_duration_seconds": 0.681
  },
  {
    "tool": "worktree_guard",
    "calls": 494,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 473,
    "error": 3,
    "avg_duration_seconds": 4.414
  },
  {
    "tool": "code_impact",
    "calls": 470,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 408,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
