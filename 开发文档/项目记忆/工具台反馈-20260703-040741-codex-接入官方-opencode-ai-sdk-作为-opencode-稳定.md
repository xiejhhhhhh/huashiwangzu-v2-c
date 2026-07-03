---
name: "工具台反馈-20260703-040741-codex-接入官方 @opencode-ai/sdk 作为 OpenCode 稳定"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-03T04:07:41.218373+00:00"
---

# MCP 使用反馈

## 任务

接入官方 @opencode-ai/sdk 作为 OpenCode 稳定主控制通路

## 顺畅度

- 评分：4/5
- 体感：工具台流程顺畅，CodeGraph、worktree_guard 和 finish_task 都有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, tail_log, opencode_gateway_status, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

新增 MCP 工具仍需重启 MCP 进程后才能出现在可调用列表；当前工作区已有大量未提交和未跟踪文件，收工输出较嘈杂。

## 缺少的工具 / 能力

希望提供 MCP 热加载/自检工具，能显示当前进程已加载的模块文件 mtime 和 tool names。

## 升级建议

opencode 工具后续可以继续增加 async prompt + event stream 订阅，以便长任务后台跟踪更细。

## 建议移除或合并的工具

无

## 其他备注

官方 SDK 主通路已实测，比 PTY/CLI 更稳定、更可跟踪。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 442,
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
    "calls": 231,
    "error": 0,
    "avg_duration_seconds": 0.322
  },
  {
    "tool": "db_schema",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "worktree_guard",
    "calls": 160,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 156,
    "error": 1,
    "avg_duration_seconds": 2.955
  },
  {
    "tool": "code_impact",
    "calls": 140,
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
    "calls": 112,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
