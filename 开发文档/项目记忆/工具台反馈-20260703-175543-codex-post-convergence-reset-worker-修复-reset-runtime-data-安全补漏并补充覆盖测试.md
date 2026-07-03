---
name: "工具台反馈-20260703-175543-codex-post-convergence-reset-worker-修复 reset_runtime_data 安全补漏并补充覆盖测试"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-post-convergence-reset-worker"
created: "2026-07-03T17:55:43.562334+00:00"
---

# MCP 使用反馈

## 任务

修复 reset_runtime_data 安全补漏并补充覆盖测试

## 顺畅度

- 评分：5/5
- 体感：整体顺畅；codegraph 定位和 finish_task 边界确认都很快。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 开工基线为 0，但并行 worker 后续写入 dev_toolkit/frontend 后，收工需要手动把这些预授权外部改动列入 baseline_paths 才能表达清楚边界。

## 缺少的工具 / 能力

无

## 升级建议

finish_task/worktree_guard 可支持“external_known_paths”语义，区别于真正开工 baseline，更适合并行子代理场景。

## 建议移除或合并的工具

无

## 其他备注

本次未 commit；只修改 reset 脚本和对应测试。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1247,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "lint",
    "calls": 650,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 554,
    "error": 8,
    "avg_duration_seconds": 0.453
  },
  {
    "tool": "code_explore",
    "calls": 526,
    "error": 0,
    "avg_duration_seconds": 0.326
  },
  {
    "tool": "call_capability",
    "calls": 495,
    "error": 17,
    "avg_duration_seconds": 0.684
  },
  {
    "tool": "run_test",
    "calls": 450,
    "error": 3,
    "avg_duration_seconds": 4.591
  },
  {
    "tool": "code_impact",
    "calls": 440,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 439,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "db_schema",
    "calls": 368,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
