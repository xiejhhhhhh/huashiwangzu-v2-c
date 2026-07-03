---
name: "工具台反馈-20260703-080607-codex-conductor-sweep-20260703-r2-主会话验收 markdown/email/structured pars"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T08:06:07.651238+00:00"
---

# MCP 使用反馈

## 任务

主会话验收 markdown/email/structured parser r2 并补修 markdown 图片重复块

## 顺畅度

- 评分：4/5
- 体感：工具台活栈验证顺畅，能明确看到 reload 后 500 收敛为 422。

## 本次用到的工具

code_explore,code_node,capabilities,routes,lint,pytest,probe,call_capability,sql,tail_log,memory_write

## 卡点 / 不顺手的地方

并行脏工作区下需要人工精确 stage；sql 查询没有字段名仍影响可读性。

## 缺少的工具 / 能力

需要一个可传文件后自动清理的临时 framework 文件夹具，方便正向 live parse 不污染 data/uploads。

## 升级建议

为 parser 类模块提供通用 bad-file_id/bad-format probe recipe；sql 保留列别名。

## 建议移除或合并的工具

无

## 其他备注

本批未创建上传文件；markdown 补修是主会话验收发现的二次问题。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 863,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 548,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "call_capability",
    "calls": 355,
    "error": 17,
    "avg_duration_seconds": 0.743
  },
  {
    "tool": "code_explore",
    "calls": 354,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "probe",
    "calls": 320,
    "error": 3,
    "avg_duration_seconds": 0.474
  },
  {
    "tool": "sql",
    "calls": 309,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 308,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 306,
    "error": 2,
    "avg_duration_seconds": 3.45
  },
  {
    "tool": "worktree_guard",
    "calls": 301,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
