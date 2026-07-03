---
name: "工具台反馈-20260703-065203-codex-frontend-shell-sweep-20260703-r2-frontend shell/runtime sweep and fix"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-frontend-shell-sweep-20260703-r2"
created: "2026-07-03T06:52:03.286809+00:00"
---

# MCP 使用反馈

## 任务

frontend shell/runtime sweep and fixes for type safety, desktop app API contract, command registry wiring, launcher search, and generated scanner hygiene.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph 和 probe 对前端契约定位很快。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, probe, agent_board_claim, agent_board_heartbeat, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 按全工作区汇总时会把并行 agent 的 backend/modules 改动一起判红；需要人工区分本 agent diff。

## 缺少的工具 / 能力

希望 worktree_guard 增加 since/owned-files 或 git pathspec 模式，用于并行 agent 场景只验证当前任务范围。

## 升级建议

finish_task 也可支持 allowed_prefixes/forbidden_prefixes，与 worktree_guard 保持一致，方便框架前端任务收尾。

## 建议移除或合并的工具

无

## 其他备注

全量 UI 二次复跑最终卡在缺 /tmp/e2e-samples/sample.docx fixture，前端启动器冒烟已单独通过。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 659,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 464,
    "error": 0,
    "avg_duration_seconds": 0.021
  },
  {
    "tool": "code_explore",
    "calls": 308,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 290,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 245,
    "error": 2,
    "avg_duration_seconds": 3.55
  },
  {
    "tool": "worktree_guard",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 232,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 200,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "call_capability",
    "calls": 188,
    "error": 12,
    "avg_duration_seconds": 0.704
  },
  {
    "tool": "probe",
    "calls": 183,
    "error": 2,
    "avg_duration_seconds": 0.452
  }
]
```
