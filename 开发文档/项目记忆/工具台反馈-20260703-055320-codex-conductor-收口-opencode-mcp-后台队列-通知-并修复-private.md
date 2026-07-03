---
name: "工具台反馈-20260703-055320-codex-conductor-收口 OpenCode MCP 后台队列/通知，并修复 private "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor"
created: "2026-07-03T05:53:20.410932+00:00"
---

# MCP 使用反馈

## 任务

收口 OpenCode MCP 后台队列/通知，并修复 private module capability 安全后准备提交推送

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台能发现 stale MCP 缓存、自检和边界守卫很有用。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, probe, mcp_self_check, memory_write, mcp_feedback, finish_task

## 卡点 / 不顺手的地方

当前 MCP stdio 进程可能持有旧模块缓存，自检结果需要用全新 Python 进程复验；lint 工具一次只支持单文件路径，多文件要分开或用 shell ruff。

## 缺少的工具 / 能力

希望 mcp_self_check 能显示 disk version 与 loaded version 是否一致；希望 opencode job notifications 可直接标出 jobs.json 与 notifications.json final_text 是否一致。

## 升级建议

给 opencode queue 增加内置 secret redaction 自检；给 subagent 完成通知增加自动 close 提醒或自动释放选项，避免 completed agent 占并发。

## 建议移除或合并的工具

无

## 其他备注

本轮发现子代理误创建用户线程的风险，应在多代理 worker 指令或工具层明确禁止非用户请求时 create_thread。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 496,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 366,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 270,
    "error": 0,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 206,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 197,
    "error": 2,
    "avg_duration_seconds": 3.201
  },
  {
    "tool": "code_impact",
    "calls": 172,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 163,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "plan_task",
    "calls": 146,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "brief",
    "calls": 139,
    "error": 0,
    "avg_duration_seconds": 0.802
  }
]
```
