---
name: "工具台反馈-20260703-065454-codex-memory-module-sweep-20260703-r2-modules/memory 扫雷并修复 experience 参数 5"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-memory-module-sweep-20260703-r2"
created: "2026-07-03T06:54:54.166037+00:00"
---

# MCP 使用反馈

## 任务

modules/memory 扫雷并修复 experience 参数 500、fallback、hit/access 计数、init 幂等治理和 save/edit 后续状态可观测性。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_reverse_audit + call_capability 很适合这种从 DB 反推链路的任务。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, call_capability, lint, run_test, tail_log, memory_write, agent_board_claim, agent_board_heartbeat, finish_task

## 卡点 / 不顺手的地方

多 agent 同时改动时 worktree_guard/finish_task 会把别人的 forbidden dirty 一起算红，需要最终报告人工解释归因。

## 缺少的工具 / 能力

希望增加按 agent claimed task 或路径白名单归因的 dirty diff 过滤视图。

## 升级建议

agent_board_claim 若任务已由同 agent claim，可返回 success:true/already_claimed，避免总控误读 rejected。

## 建议移除或合并的工具

无

## 其他备注

活系统 capability registry 对已注册函数的返回形状可能需要后端重载才完全反映，工具台若能提示当前代码热加载状态会更稳。

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
    "calls": 468,
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
    "calls": 250,
    "error": 2,
    "avg_duration_seconds": 3.494
  },
  {
    "tool": "worktree_guard",
    "calls": 245,
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
    "tool": "call_capability",
    "calls": 202,
    "error": 12,
    "avg_duration_seconds": 0.681
  },
  {
    "tool": "db_schema",
    "calls": 200,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 184,
    "error": 2,
    "avg_duration_seconds": 0.451
  }
]
```
