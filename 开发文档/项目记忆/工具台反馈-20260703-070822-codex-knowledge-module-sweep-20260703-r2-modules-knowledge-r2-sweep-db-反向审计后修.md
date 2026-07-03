---
name: "工具台反馈-20260703-070822-codex-knowledge-module-sweep-20260703-r2-modules/knowledge r2 sweep：DB 反向审计后修"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-knowledge-module-sweep-20260703-r2"
created: "2026-07-03T07:08:22.138963+00:00"
---

# MCP 使用反馈

## 任务

modules/knowledge r2 sweep：DB 反向审计后修复 evidence/chunk_entity、owner scope、vector dim mismatch、pipeline task lookup、测试初始化与清理。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_reverse_audit/capability/probe/run_test 对本任务很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_impact, capabilities, db_reverse_audit, sql, lint, run_test, probe, call_capability, finish_task, memory_write, agent_board_claim, agent_board_heartbeat, agent_board_complete

## 卡点 / 不顺手的地方

finish_task 只按 module_key=knowledge 判边界，无法把 开发文档/项目记忆 作为允许前缀，也无法区分其他 agent 已存在脏文件，导致收工 success=false 但实际本任务边界 OK。工具台 SQL 与本地命令 DB_NAME 差异也容易误判清理结果。

## 缺少的工具 / 能力

建议提供只清本 agent 创建测试数据的 DML helper 或 test-artifact cleanup helper；finish_task 支持 allowed_prefixes 和 known_foreign_dirty 参数。

## 升级建议

worktree_guard/finish_task 可输出“本任务新增/修改候选”和“外部既有脏文件”分层；sql 工具可显示连接 DB_NAME，避免中文/英文库混淆。

## 建议移除或合并的工具

无

## 其他备注

本轮最终验证：ruff passed；knowledge backend+sandbox 45 passed；knowledge search/get_page_fusion capabilities success；dashboard/pipeline-debt probes success；测试前缀残留文档为 0。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 694,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 486,
    "error": 0,
    "avg_duration_seconds": 0.022
  },
  {
    "tool": "code_explore",
    "calls": 320,
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
    "calls": 273,
    "error": 2,
    "avg_duration_seconds": 3.74
  },
  {
    "tool": "worktree_guard",
    "calls": 257,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 245,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "call_capability",
    "calls": 243,
    "error": 12,
    "avg_duration_seconds": 0.632
  },
  {
    "tool": "db_schema",
    "calls": 209,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 195,
    "error": 2,
    "avg_duration_seconds": 0.447
  }
]
```
