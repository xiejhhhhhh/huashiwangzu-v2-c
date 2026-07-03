---
name: "工具台反馈-20260703-183802-codex-post-convergence-repair-post-convergence repair 提交前补漏：job 状态"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-post-convergence-repair"
created: "2026-07-03T18:38:02.783072+00:00"
---

# MCP 使用反馈

## 任务

post-convergence repair 提交前补漏：job 状态语义、文件锁、stale/orphan、sandbox Python 统一、提交级验收。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，worktree_guard 很快暴露了模块专项变更混入的问题。

## 本次用到的工具

codegraph CLI, worktree_guard, probe, memory_write, mcp_feedback, subagent worker

## 卡点 / 不顺手的地方

同一工作区并行出现模块专项变更，导致 post-convergence 分支整体提交边界不干净；release_gate full 第一次出现 excel-engine sandbox 瞬时失败，单跑和全矩阵复跑均通过。

## 缺少的工具 / 能力

希望 worktree_guard 能支持保存/对比本轮基线，直接标注哪些 dirty 是本轮新增、哪些是后续混入。

## 升级建议

tool_job_status 新增的状态字段后续可沉到项目工具台 UI，展示 job_success/command_success/clean_success/release_safe 四象限。

## 建议移除或合并的工具

无。

## 其他备注

本轮没有提交。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1311,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "lint",
    "calls": 654,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 574,
    "error": 8,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 563,
    "error": 0,
    "avg_duration_seconds": 0.326
  },
  {
    "tool": "call_capability",
    "calls": 499,
    "error": 17,
    "avg_duration_seconds": 0.681
  },
  {
    "tool": "worktree_guard",
    "calls": 468,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 466,
    "error": 3,
    "avg_duration_seconds": 4.454
  },
  {
    "tool": "code_impact",
    "calls": 455,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 370,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
