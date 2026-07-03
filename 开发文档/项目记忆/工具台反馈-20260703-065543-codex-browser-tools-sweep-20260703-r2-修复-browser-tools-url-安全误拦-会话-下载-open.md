---
name: "工具台反馈-20260703-065543-codex-browser-tools-sweep-20260703-r2-修复 browser-tools URL 安全误拦、会话/下载/open"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-browser-tools-sweep-20260703-r2"
created: "2026-07-03T06:55:43.403091+00:00"
---

# MCP 使用反馈

## 任务

修复 browser-tools URL 安全误拦、会话/下载/open schema 与 manifest/sandbox 契约漂移，消除 agent tool guidance 中 6 个 browser-tools 失败

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/capabilities/code_node 能很快定位契约漂移和测试失败来源。

## 本次用到的工具

brief, plan_task, worktree_guard, agent_board_claim, code_explore, code_node, code_impact, routes, db_schema, capabilities, lint, probe, call_capability, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的模块边界检查在共享脏工作区里只能给全局失败，无法标注开工前已存在的外部改动基线；agent_board_claim 也不能作为同 owner heartbeat 更新。

## 缺少的工具 / 能力

希望增加 agent_board_heartbeat/update_note；希望 worktree_guard/finish_task 支持传入 baseline 或 allowed_prefixes 额外包含项目记忆。

## 升级建议

finish_task 可展示“本次新增改动”与“开工前已有改动”的差异基线，适合多 agent 共享分支。

## 建议移除或合并的工具

无

## 其他备注

活栈 call_capability 对 Google 仍命中旧代码的 DNS 拦截，说明常驻后端未重启；为避免干扰并行 agent，本次没有强制重启。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 673,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 468,
    "error": 0,
    "avg_duration_seconds": 0.021
  },
  {
    "tool": "code_explore",
    "calls": 310,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 291,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 252,
    "error": 2,
    "avg_duration_seconds": 3.473
  },
  {
    "tool": "worktree_guard",
    "calls": 245,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 238,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 203,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "call_capability",
    "calls": 202,
    "error": 12,
    "avg_duration_seconds": 0.681
  },
  {
    "tool": "probe",
    "calls": 184,
    "error": 2,
    "avg_duration_seconds": 0.451
  }
]
```
