---
name: "工具台反馈-20260703-053545-codex-devtool-worker-收口 dev_toolkit/OpenCode MCP 红点并加固 op"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-devtool-worker"
created: "2026-07-03T05:35:45.384409+00:00"
---

# MCP 使用反馈

## 任务

收口 dev_toolkit/OpenCode MCP 红点并加固 opencode_queue 跨进程监控锁

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/codegraph/finish 串起来很好用。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, mcp_self_check, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

lint 工具的 path 参数只支持单文件，但错误信息足够清楚；多文件 lint 仍需 shell 或逐文件调用。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 能支持 allowed_prefixes，便于全局任务但只允许 dev_toolkit 的边界验收。

## 升级建议

lint 可支持逗号/空格分隔多路径，finish_task 可暴露 allowed_prefixes 参数。

## 建议移除或合并的工具

无

## 其他备注

本轮遵守只改 dev_toolkit；项目记忆和反馈为强制收尾留痕。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 466,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 357,
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
    "calls": 258,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 191,
    "error": 2,
    "avg_duration_seconds": 3.153
  },
  {
    "tool": "worktree_guard",
    "calls": 190,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 163,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "code_impact",
    "calls": 158,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "plan_task",
    "calls": 135,
    "error": 0,
    "avg_duration_seconds": 0.007
  },
  {
    "tool": "probe",
    "calls": 132,
    "error": 0,
    "avg_duration_seconds": 0.475
  }
]
```
