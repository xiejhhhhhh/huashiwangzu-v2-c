---
name: "工具台反馈-20260703-023125-opencode-业务模块-P1-Memory向量回填和memory_links建链治理"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode"
created: "2026-07-03T02:31:25.044301+00:00"
---

# MCP 使用反馈

## 任务

业务模块-P1-Memory向量回填和memory_links建链治理

## 顺畅度

- 评分：4/5
- 体感：基本顺畅，但调试自动建链问题时耗费了较多轮次（向量回填代码本身没问题，但 raw SQL 返回类型和 session expire 两个坑花时间排查）

## 本次用到的工具

code_explore, code_node, call_capability, lint, sql, tail_log, db_schema, routes, capabilities, worktree_guard, restart_backend, mailbox_create_delivery_bundle, mailbox_check_delivery_bundle, memory_write

## 卡点 / 不顺手的地方

后端日志查看不方便（tail_log 返回空，需手动 grep modules.log）；自动建链的调试需要多次重启后端和等待 background task

## 缺少的工具 / 能力

无

## 升级建议

tail_log 工具如果后端日志在 modules.log 中，应能自动查找到正确的日志文件

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 441,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 310,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 227,
    "error": 0,
    "avg_duration_seconds": 0.321
  },
  {
    "tool": "db_schema",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 156,
    "error": 1,
    "avg_duration_seconds": 2.955
  },
  {
    "tool": "worktree_guard",
    "calls": 153,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 138,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "probe",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.485
  },
  {
    "tool": "plan_task",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
