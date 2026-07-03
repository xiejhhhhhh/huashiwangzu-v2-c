---
name: "工具台反馈-20260703-080324-codex-structured-parser-sweep-20260703-r2-modules/structured-parser r2 sweep h"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-structured-parser-sweep-20260703-r2"
created: "2026-07-03T08:03:24.337454+00:00"
---

# MCP 使用反馈

## 任务

modules/structured-parser r2 sweep hardened JSON/YAML parsing boundaries and sandbox production-code coverage.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/lint/run_test/finish_task 串起来能形成完整证据链。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的模块边界检查会把开工前已有的其他 agent 脏文件和项目记忆一起算成失败，无法表达“本 agent 实际改动范围合规但共享工作区不干净”。live call_capability 也受常驻后端未 reload 影响，容易把已修代码误报为仍失败。

## 缺少的工具 / 能力

缺少一个按 agent/时间或指定路径白名单做 scoped dirty diff 的收工边界工具；缺少不重启共享活栈即可临时加载单模块新代码的 probe/call_capability 隔离模式。

## 升级建议

finish_task 可支持 allowed_prefixes 追加项目记忆 slug 前缀，并显示 since-start baseline diff；call_capability 可提示当前后端进程启动时间/模块文件 mtime，判断是否需要 reload。

## 建议移除或合并的工具

无

## 其他备注

本次没有修改 backend/app、frontend/src、其他 modules 或 data/uploads。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 854,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 545,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "code_explore",
    "calls": 350,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 347,
    "error": 17,
    "avg_duration_seconds": 0.755
  },
  {
    "tool": "probe",
    "calls": 312,
    "error": 3,
    "avg_duration_seconds": 0.476
  },
  {
    "tool": "sql",
    "calls": 308,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 306,
    "error": 2,
    "avg_duration_seconds": 3.45
  },
  {
    "tool": "code_impact",
    "calls": 303,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "worktree_guard",
    "calls": 299,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 239,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
