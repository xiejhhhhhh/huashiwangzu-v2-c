---
name: "工具台反馈-20260703-075412-codex-conductor-sweep-20260703-r2-主会话验收 docx/xlsx parser r2 并补修 docx 坏"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:54:12.893449+00:00"
---

# MCP 使用反馈

## 任务

主会话验收 docx/xlsx parser r2 并补修 docx 坏参数 500

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台能快速暴露边界、路由、能力和真实 HTTP 结果。

## 本次用到的工具

brief,plan_task,worktree_guard,code_explore,code_node,code_impact,routes,capabilities,lint,run_test/probe/call_capability,sql,db_schema,tail_log,finish_task,memory_write

## 卡点 / 不顺手的地方

sql 工具返回列名为 col0/col1 不保留字段别名，可读性稍差；finish_task 在并行脏工作区下会整体标红，需要主会话自行解释。

## 缺少的工具 / 能力

希望有按路径精确 stage/commit 前验收清单工具，能自动排除其他代理脏改。

## 升级建议

为 call_capability 增加期望状态码/断言模式；sql 结果保留字段名；worktree_guard 支持忽略指定前缀用于并行工作流。

## 建议移除或合并的工具

无

## 其他备注

本轮再次确认 --workers 3 下需要杀 uvicorn 父进程确保加载新代码。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 794,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 531,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 340,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 332,
    "error": 17,
    "avg_duration_seconds": 0.701
  },
  {
    "tool": "sql",
    "calls": 306,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 299,
    "error": 2,
    "avg_duration_seconds": 3.516
  },
  {
    "tool": "worktree_guard",
    "calls": 292,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 291,
    "error": 2,
    "avg_duration_seconds": 0.492
  },
  {
    "tool": "code_impact",
    "calls": 284,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "db_schema",
    "calls": 233,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
