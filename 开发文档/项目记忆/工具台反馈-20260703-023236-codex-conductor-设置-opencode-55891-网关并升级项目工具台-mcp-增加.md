---
name: "工具台反馈-20260703-023236-codex-conductor-设置 opencode 55891 网关并升级项目工具台 MCP 增加 "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor"
created: "2026-07-03T02:32:36.743005+00:00"
---

# MCP 使用反馈

## 任务

设置 opencode 55891 网关并升级项目工具台 MCP 增加 opencode 派发工具

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；工具台组件化接入清晰。

## 本次用到的工具

plan_task, worktree_guard, code_explore, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前 live MCP 进程不会热加载新增工具，需要重启 MCP 才能使用 opencode_*；opencode serve 普通无 TTY 后台启动曾误报，需要用 script 伪终端并轮询监听。

## 缺少的工具 / 能力

缺一个 MCP 热重载/自重启工具；也缺 opencode dispatch 状态聚合工具，后续可补。

## 升级建议

给 dev_toolkit 增加 mcp_reload_self 或在文档明确重启方式；opencode_tools 后续可加 opencode_dispatch_status、opencode_claim_and_dispatch。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 441,
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
    "calls": 227,
    "error": 0,
    "avg_duration_seconds": 0.321
  },
  {
    "tool": "db_schema",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 156,
    "error": 1,
    "avg_duration_seconds": 2.955
  },
  {
    "tool": "worktree_guard",
    "calls": 153,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 138,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "probe",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.485
  },
  {
    "tool": "plan_task",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
