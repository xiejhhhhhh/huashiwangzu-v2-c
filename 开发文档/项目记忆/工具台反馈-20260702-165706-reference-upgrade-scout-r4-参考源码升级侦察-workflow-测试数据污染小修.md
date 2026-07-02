---
name: "工具台反馈-20260702-165706-reference-upgrade-scout-r4-参考源码升级侦察 + workflow 测试数据污染小修"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "reference-upgrade-scout-r4"
created: "2026-07-02T16:57:06.933656+00:00"
---

# MCP 使用反馈

## 任务

参考源码升级侦察 + workflow 测试数据污染小修

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_reverse_audit + routes/probe 很快把 skeleton 表和活系统污染串起来。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, db_schema, db_reverse_audit, routes, capabilities, probe, sql, memory_search, memory_write, finish_task, mcp_feedback

## 卡点 / 不顺手的地方

capabilities 输出过长且截断，做全局能力对齐时仍需要更精简的 drift 摘要；git status 对中文未跟踪文件默认转义，人工阅读不太舒服。

## 缺少的工具 / 能力

建议新增 reference_sources_scan，自动列参考项目、README、关键架构文件和上次读取时间；建议 db_reverse_audit 输出可选 compact/table-only 模式。

## 升级建议

把本轮报告中的 devtool durable board、workflow orchestrator、private module lifecycle、chunked upload、parser quality profile 拆成可派 worker 的任务模板。

## 建议移除或合并的工具

无

## 其他备注

本轮发现并修复 backend/tests/test_platform_workflow_ledger.py 清理条件错误，避免继续污染 framework_workflow_* 活库。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 389,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 269,
    "error": 0,
    "avg_duration_seconds": 0.016
  },
  {
    "tool": "sql",
    "calls": 198,
    "error": 8,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 189,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "code_impact",
    "calls": 123,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 2.258
  },
  {
    "tool": "db_schema",
    "calls": 114,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 102,
    "error": 0,
    "avg_duration_seconds": 0.527
  },
  {
    "tool": "plan_task",
    "calls": 84,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
