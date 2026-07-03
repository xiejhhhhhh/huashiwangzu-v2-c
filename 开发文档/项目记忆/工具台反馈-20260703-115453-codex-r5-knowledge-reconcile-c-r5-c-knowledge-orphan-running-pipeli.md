---
name: "工具台反馈-20260703-115453-codex-r5-knowledge-reconcile-c-R5 C knowledge orphan running pipeli"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-r5-knowledge-reconcile-c"
created: "2026-07-03T11:54:53.631672+00:00"
---

# MCP 使用反馈

## 任务

R5 C knowledge orphan running pipeline runs guarded reconcile dry-run/apply implementation

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 toolkit 能快速定位 debt/orchestrator/router/test 影响面。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

并行 worker 的未提交改动会让 finish_task/worktree_guard 以全局 dirty 失败，尽管本 worker 自己只碰 allowed files；需要人工区分归因。

## 缺少的工具 / 能力

希望 worktree_guard 支持传入本 agent touched files 或 since-start baseline，用于并行场景下判断本 worker 是否越界。

## 升级建议

finish_task 可以展示 start snapshot diff 或支持 ignore-existing-dirty，避免并行任务都被其他泳道改动染红。

## 建议移除或合并的工具

无

## 其他备注

活栈只读 dry-run 返回数据很大，probe 如能支持 json path/summary 提取会更省输出。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1137,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 628,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 502,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 485,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 471,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "call_capability",
    "calls": 458,
    "error": 17,
    "avg_duration_seconds": 0.709
  },
  {
    "tool": "run_test",
    "calls": 415,
    "error": 2,
    "avg_duration_seconds": 3.262
  },
  {
    "tool": "code_impact",
    "calls": 403,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 340,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
