---
name: "工具台反馈-20260703-050353-codex-补齐 OpenCode MCP 后台任务终态通知收件箱，让 job 完成"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-03T05:03:53.332718+00:00"
---

# MCP 使用反馈

## 任务

补齐 OpenCode MCP 后台任务终态通知收件箱，让 job 完成/失败/超时后能落盘成未读通知，供 Codex 主线程或 watcher 接手。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，现有工具台足够完成实现和验证；当前进程模块缓存导致自检看不到新工具，需要重启后才完整生效。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, mcp_self_check, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前 MCP 不支持热加载，mcp_self_check 在当前进程中仍显示旧 opencode_tools 工具列表；只能用新 Python 进程和 test_mcp_entry 验证重启后的工具列表。

## 缺少的工具 / 能力

希望后续有 MCP restart/reload 工具，或者 self_check 能标明 on-disk tool_definitions 与当前已加载模块的差异。

## 升级建议

下一步可以做一个外层 automation/watcher：定时调用 opencode_sdk_job_notifications，发现 unread 后唤醒/提醒 Codex 线程，并在接手后 mark_read。

## 建议移除或合并的工具

无

## 其他备注

这轮把“发起任务 -> MCP 后台轮询 -> 终态通知 -> Codex 接手”的闭环补到了工具层。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 319,
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
    "calls": 234,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "worktree_guard",
    "calls": 165,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 160,
    "error": 1,
    "avg_duration_seconds": 2.928
  },
  {
    "tool": "code_impact",
    "calls": 143,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "probe",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.483
  },
  {
    "tool": "plan_task",
    "calls": 115,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
