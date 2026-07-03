---
name: "工具台反馈-20260703-034715-codex-完善 OpenCode Desktop sidecar 直连调研并加固 "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-03T03:47:15.945918+00:00"
---

# MCP 使用反馈

## 任务

完善 OpenCode Desktop sidecar 直连调研并加固 opencode headless/PTY 工具链

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/codegraph/finish_task 都能串起来。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_impact, tail_log, opencode_gateway_status, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前 MCP 进程热加载不了刚改的 opencode_tools.py，需要重启后新实现才生效；opencode_server 日志里已有 script 包装留下的 JSON-RPC 污染。

## 缺少的工具 / 能力

希望 opencode tools 增加 reload/version 自检，显示当前 MCP 进程加载的文件 mtime 和工具实现版本。

## 升级建议

给 opencode_dispatch_letter 增加 PTY fallback 或后台进程启动期健康检查结果展示；给 opencode_pty_* 增加按 log_path 续读能力，避免 MCP 重启后丢失 session 引用。

## 建议移除或合并的工具

无

## 其他备注

桌面 sidecar 不建议直连，固定 headless 55891 是更稳的控制面。

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
    "calls": 229,
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
    "calls": 158,
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
    "calls": 111,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
