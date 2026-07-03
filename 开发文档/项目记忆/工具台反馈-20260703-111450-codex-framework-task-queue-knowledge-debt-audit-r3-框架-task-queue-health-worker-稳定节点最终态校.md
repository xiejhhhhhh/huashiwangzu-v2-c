---
name: "工具台反馈-20260703-111450-codex-framework-task-queue-knowledge-debt-audit-r3-框架 task_queue health/worker 稳定节点最终态校"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-framework-task-queue-knowledge-debt-audit-r3"
created: "2026-07-03T11:14:50.067833+00:00"
---

# MCP 使用反馈

## 任务

框架 task_queue health/worker 稳定节点最终态校正

## 顺畅度

- 评分：4/5
- 体感：聚焦测试与 ruff 顺畅；并发工作区中同一 health 口径被其他编辑改变，最终按磁盘态和测试态校正记忆。

## 本次用到的工具

codegraph CLI, git status/diff, pytest, ruff, curl health, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

项目工具台 MCP 未直接暴露；并发编辑同一框架文件时缺少锁/owner 提示，容易出现记忆与最终磁盘态不一致。

## 缺少的工具 / 能力

需要可直接调用的 worktree_guard/agent_board_heartbeat，并希望 worktree_guard 能提示目标文件最近是否被其他 agent 改写。

## 升级建议

给 dev_toolkit 增加 CLI call_tool wrapper；agent_board 可增加 per-file claim 或最近编辑 owner 提示。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1114,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 614,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 453,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 448,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 447,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 444,
    "error": 17,
    "avg_duration_seconds": 0.722
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 392,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 371,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 317,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
