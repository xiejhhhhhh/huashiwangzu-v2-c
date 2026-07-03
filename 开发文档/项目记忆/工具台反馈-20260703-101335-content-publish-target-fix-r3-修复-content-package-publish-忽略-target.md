---
name: "工具台反馈-20260703-101335-content-publish-target-fix-r3-修复 Content Package publish 忽略 target"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "content-publish-target-fix-r3"
created: "2026-07-03T10:13:35.141479+00:00"
---

# MCP 使用反馈

## 任务

修复 Content Package publish 忽略 target_file_id，按 artifact/file replace 语义写入目标文件并补回归测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 很快定位到 content publish 忽略 target_file_id 以及 artifact_service 的 replace/target 权限链。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 在多 agent 并行时会把他人 dirty 和本任务 dirty 混在一起，需要额外用 git diff pathspec 说明实际改动范围。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 支持传入本 agent claimed paths 或 baseline snapshot，区分开工后他人新增 dirty。

## 升级建议

给 finish_task 增加 allowed_prefixes 参数并在报告里单列 matching_diff/outside_diff，会更适合多 agent 并行收尾。

## 建议移除或合并的工具

无

## 其他备注

未 commit / 未 push。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1025,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 585,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 415,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 393,
    "error": 17,
    "avg_duration_seconds": 0.78
  },
  {
    "tool": "probe",
    "calls": 369,
    "error": 3,
    "avg_duration_seconds": 0.456
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 362,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 349,
    "error": 2,
    "avg_duration_seconds": 3.257
  },
  {
    "tool": "worktree_guard",
    "calls": 337,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 284,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
