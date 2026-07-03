---
name: "工具台反馈-20260703-090424-codex-conductor-sweep-20260703-r2-Main-session validation for douyin-d"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T09:04:24.121757+00:00"
---

# MCP 使用反馈

## 任务

Main-session validation for douyin-delivery, office-gen, scheduler r2 leftovers after subagent 502

## 顺畅度

- 评分：4/5
- 体感：工具台验证路径顺畅，call_capability 和 run_test 很快暴露了 scheduler sandbox 的真实导入问题。

## 本次用到的工具

probe, call_capability, lint, run_test, tail_log, code_node, code_impact, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

子代理 502 后主会话需要手动区分已验收半成品、未验收记忆和历史 uploads；finish_task 对并行脏工作区仍不够精确。

## 缺少的工具 / 能力

需要一个按显式文件列表做 staged-ready 边界验收的工具，以及对历史数据污染的只读摘要工具直接输出清理 SQL 草案。

## 升级建议

子代理 502 恢复策略应先 resume/send_input，而不是立即 close；工具台可记录代理错误与后续主会话接管关系。

## 建议移除或合并的工具

无

## 其他备注

已接受用户反馈：后续代理卡住恢复后优先发继续消息，不直接杀掉重来。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 893,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 562,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "call_capability",
    "calls": 379,
    "error": 17,
    "avg_duration_seconds": 0.796
  },
  {
    "tool": "code_explore",
    "calls": 366,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "probe",
    "calls": 331,
    "error": 3,
    "avg_duration_seconds": 0.468
  },
  {
    "tool": "code_impact",
    "calls": 324,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 317,
    "error": 2,
    "avg_duration_seconds": 3.357
  },
  {
    "tool": "sql",
    "calls": 310,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 310,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 248,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
