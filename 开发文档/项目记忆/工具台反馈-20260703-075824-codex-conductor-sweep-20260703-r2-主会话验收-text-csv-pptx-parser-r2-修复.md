---
name: "工具台反馈-20260703-075824-codex-conductor-sweep-20260703-r2-主会话验收 text/csv/pptx parser r2 修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:58:24.282160+00:00"
---

# MCP 使用反馈

## 任务

主会话验收 text/csv/pptx parser r2 修复

## 顺畅度

- 评分：4/5
- 体感：工具台验活栈和能力很顺，能快速区分 sandbox 成功与活栈坏参。

## 本次用到的工具

code_explore,capabilities,lint,pytest,sql,probe,call_capability,tail_log,memory_write

## 卡点 / 不顺手的地方

sql 结果字段仍是 col0/col1；并行脏工作区下 finish_task 不适合直接作为通过/失败结论。

## 缺少的工具 / 能力

希望有按模块生成精确 stage 清单并自动排除其他代理改动的工具。

## 升级建议

probe/call_capability 支持断言 expected_status/expected_success 会更省主会话 token。

## 建议移除或合并的工具

无

## 其他备注

本批没有新增上传数据；csv/pptx 无现成正向 framework 文件，未强行造数据。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 830,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 534,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "code_explore",
    "calls": 347,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 337,
    "error": 17,
    "avg_duration_seconds": 0.694
  },
  {
    "tool": "sql",
    "calls": 307,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 300,
    "error": 3,
    "avg_duration_seconds": 0.485
  },
  {
    "tool": "run_test",
    "calls": 300,
    "error": 2,
    "avg_duration_seconds": 3.506
  },
  {
    "tool": "worktree_guard",
    "calls": 295,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 288,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "db_schema",
    "calls": 236,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
