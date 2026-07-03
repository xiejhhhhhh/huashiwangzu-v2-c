---
name: "工具台反馈-20260703-100625-knowledge-file-lifecycle-audit-r3-只读审计 knowledge 文件生命周期与历史 kb_pipeline"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "knowledge-file-lifecycle-audit-r3"
created: "2026-07-03T10:06:25.160636+00:00"
---

# MCP 使用反馈

## 任务

只读审计 knowledge 文件生命周期与历史 kb_pipeline failed 债务，输出 P0/P1/P2 证据和修复边界。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph、SQL、probe、capability 能把代码和活数据闭环串起来。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, db_schema, db_reverse_audit, sql, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

SQL 工具返回列名为 col0/col1，复杂聚合需要人工对照查询列顺序；finish_task 对只读审计遇到他人并发 dirty 会直接 success=false，需要在最终报告中特别说明。

## 缺少的工具 / 能力

希望有知识库生命周期专用审计工具：一键输出 kb_documents/kb_chunks/framework_file_items/source_state/task_debt 的命名列汇总和样本。

## 升级建议

db_reverse_audit 可增加 foreign-key/lifecycle join 模板，尤其是按 source file live/deleted/missing 分类 business rows。

## 建议移除或合并的工具

无

## 其他备注

本次未执行任何写入型修复或 pipeline-debt apply；仅 memory_write/mcp_feedback 按项目规则落盘。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1008,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 578,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 405,
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
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 366,
    "error": 3,
    "avg_duration_seconds": 0.458
  },
  {
    "tool": "code_impact",
    "calls": 355,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 339,
    "error": 2,
    "avg_duration_seconds": 3.19
  },
  {
    "tool": "worktree_guard",
    "calls": 329,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 278,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
