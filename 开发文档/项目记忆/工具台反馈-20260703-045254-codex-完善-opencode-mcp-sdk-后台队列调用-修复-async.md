---
name: "工具台反馈-20260703-045254-codex-完善 OpenCode MCP SDK 后台队列调用：修复 async "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-03T04:52:54.238649+00:00"
---

# MCP 使用反馈

## 任务

完善 OpenCode MCP SDK 后台队列调用：修复 async 空壳 assistant 假完成，支持非终态 job 重挂监控，并补齐 job 工具入口测试与 README 说明。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，tool_search 能看到更新后的 opencode job 工具，CodeGraph 和 self_check 定位很快。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, agent_activity_report, mcp_self_check, opencode_gateway_status, opencode_sdk_smoke, opencode_sdk_job_list, lint, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前 MCP 进程不会热加载新 Python 代码，修复后的 opencode_queue 只能通过新进程测试验证，需重启 MCP 才能在当前工具调用中生效；工作区有很多既有 dirty/untracked 文件，边界输出较嘈杂。

## 缺少的工具 / 能力

希望有 MCP 热重载或至少 restart/self-reload 工具，能安全重启当前项目工具台并重新暴露更新后的工具实现。

## 升级建议

opencode_sdk_job_status 可以后续增加更紧凑的 summary 输出，避免 messages/parts 太长时占用大量上下文。

## 建议移除或合并的工具

无

## 其他备注

本次发现并修复了 promptAsync 初始空 assistant 被 cost/tokens 误判为 completed 的假绿。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 445,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 315,
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
    "calls": 233,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "worktree_guard",
    "calls": 163,
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
    "calls": 159,
    "error": 1,
    "avg_duration_seconds": 2.935
  },
  {
    "tool": "code_impact",
    "calls": 142,
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
    "calls": 114,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
