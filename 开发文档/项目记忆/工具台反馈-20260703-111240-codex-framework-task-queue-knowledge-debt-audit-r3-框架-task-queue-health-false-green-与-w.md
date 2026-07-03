---
name: "工具台反馈-20260703-111240-codex-framework-task-queue-knowledge-debt-audit-r3-框架 task_queue health false-green 与 w"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-framework-task-queue-knowledge-debt-audit-r3"
created: "2026-07-03T11:12:40.191858+00:00"
---

# MCP 使用反馈

## 任务

框架 task_queue health false-green 与 worker 并发恢复稳定节点

## 顺畅度

- 评分：4/5
- 体感：MCP callable tools 未在当前会话暴露，但可复用 dev_toolkit 组件完成标准落盘；CodeGraph CLI 和聚焦测试链路顺畅。

## 本次用到的工具

codegraph CLI, git status, pytest, ruff, curl health, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

tool_search 未发现项目工具台 MCP 工具，无法直接调用 brief/plan_task/worktree_guard/probe/tail_log，只能用 CLI/组件函数等价执行。

## 缺少的工具 / 能力

希望当前 Codex 会话能直接暴露项目工具台 MCP 工具，尤其 memory_write/mcp_feedback/agent_board_heartbeat。

## 升级建议

为 dev_toolkit 提供一个稳定的非 stdio CLI wrapper，例如 python dev_toolkit/call_tool.py <tool> <json>，方便 MCP 未挂载时仍按工具协议执行。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1112,
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
    "calls": 450,
    "error": 5,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "code_explore",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 444,
    "error": 17,
    "avg_duration_seconds": 0.722
  },
  {
    "tool": "sql",
    "calls": 442,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 370,
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
