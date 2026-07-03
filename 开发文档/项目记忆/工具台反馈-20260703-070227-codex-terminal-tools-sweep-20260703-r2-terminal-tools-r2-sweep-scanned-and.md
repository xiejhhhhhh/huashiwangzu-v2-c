---
name: "工具台反馈-20260703-070227-codex-terminal-tools-sweep-20260703-r2-terminal-tools r2 sweep: scanned and"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-terminal-tools-sweep-20260703-r2"
created: "2026-07-03T07:02:27.052172+00:00"
---

# MCP 使用反馈

## 任务

terminal-tools r2 sweep: scanned and hardened workspace boundary/path sanitize/command blocking/file bridge/fake-success/test cleanup within modules/terminal-tools only.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/capability/probe/run_test/finish_task 链路完整，能快速形成证据闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, agent_board_claim, agent_board_heartbeat, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, lint, run_test, call_capability, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task/worktree_guard 在并行 worker 场景会用全局 dirty 判失败，虽然能看到 forbidden_hits=0，但 success=false 容易掩盖当前 worker 的模块内改动已合规。

## 缺少的工具 / 能力

希望有一个 worker-scoped boundary summary 工具，直接输出 `git diff --name-only -- modules/{key}` 与 allowed memory paths，并将其他并行 dirty 归类为 external noise。

## 升级建议

finish_task 可增加 `ignore_external_dirty=true` 或 `report_external_dirty_only=true`，在多 worker sweep 中减少误报；call_capability 若能记录并返回测试数据清理提示会更稳。

## 建议移除或合并的工具

无

## 其他备注

活系统验证中测试文件 codex_terminal_sweep_r2.txt 已通过 terminal-tools 自身 exec rm 清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 689,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 483,
    "error": 0,
    "avg_duration_seconds": 0.022
  },
  {
    "tool": "code_explore",
    "calls": 314,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 294,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 269,
    "error": 2,
    "avg_duration_seconds": 3.785
  },
  {
    "tool": "worktree_guard",
    "calls": 248,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "call_capability",
    "calls": 220,
    "error": 12,
    "avg_duration_seconds": 0.671
  },
  {
    "tool": "db_schema",
    "calls": 205,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 190,
    "error": 2,
    "avg_duration_seconds": 0.45
  }
]
```
