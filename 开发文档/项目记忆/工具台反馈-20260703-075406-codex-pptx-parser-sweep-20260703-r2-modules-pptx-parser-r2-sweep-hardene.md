---
name: "工具台反馈-20260703-075406-codex-pptx-parser-sweep-20260703-r2-modules/pptx-parser r2 sweep hardene"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-pptx-parser-sweep-20260703-r2"
created: "2026-07-03T07:54:06.049659+00:00"
---

# MCP 使用反馈

## 任务

modules/pptx-parser r2 sweep hardened parse validation and real sandbox coverage

## 顺畅度

- 评分：4/5
- 体感：工具台整体顺畅，brief/plan/worktree/codegraph/lint/run_test/probe 能把模块扫雷闭环串起来。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的 module_key 边界检查不能表达“模块目录 + 自己的项目记忆”这个允许集，在多人共享脏工作区里会整体 success=false，需要人工解释。

## 缺少的工具 / 能力

希望 finish_task 支持 allowed_prefixes 或 owned_memory_slugs，以便模块任务允许自己的记忆文件同时过滤其他 agent 脏项。

## 升级建议

worktree_guard/finish_task 可以输出 matched_allowed 与 outside_unrelated 分组，并允许传入 baseline 时间或 agent 名来区分本次新增记忆。

## 建议移除或合并的工具

无

## 其他备注

run_test 走 pytest 暴露了 sandbox 脚本没有 pytest 入口的问题，很有帮助。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 794,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 531,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 340,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 332,
    "error": 17,
    "avg_duration_seconds": 0.701
  },
  {
    "tool": "sql",
    "calls": 306,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 299,
    "error": 2,
    "avg_duration_seconds": 3.516
  },
  {
    "tool": "worktree_guard",
    "calls": 292,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 291,
    "error": 2,
    "avg_duration_seconds": 0.492
  },
  {
    "tool": "code_impact",
    "calls": 284,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "db_schema",
    "calls": 233,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
