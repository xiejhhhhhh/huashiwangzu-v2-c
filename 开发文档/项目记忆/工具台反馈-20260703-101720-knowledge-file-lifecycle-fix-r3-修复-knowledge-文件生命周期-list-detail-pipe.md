---
name: "工具台反馈-20260703-101720-knowledge-file-lifecycle-fix-r3-修复 knowledge 文件生命周期 list/detail/pipe"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "knowledge-file-lifecycle-fix-r3"
created: "2026-07-03T10:17:20.063671+00:00"
---

# MCP 使用反馈

## 任务

修复 knowledge 文件生命周期 list/detail/pipeline 行为并补测试。

## 顺畅度

- 评分：5/5
- 体感：整体顺畅，CodeGraph 很快定位了 document_service/pipeline_service/source_file_state 的调用关系。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 对共享工作区会整体报 false，需要人工区分本 agent 改动与其他 agent 已有改动。

## 缺少的工具 / 能力

希望 worktree_guard 支持 baseline 参数或 since-start 快照，只报告本 agent 新增越界。

## 升级建议

finish_task 可接受 acknowledged_outside_changes 列表，避免多人并行时误判收工边界。

## 建议移除或合并的工具

无

## 其他备注

run_test 对缺 JWT_SECRET 的模块测试没有自动注入默认测试 secret，但错误清晰，已在测试文件内补 setdefault。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1027,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 593,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 416,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 396,
    "error": 17,
    "avg_duration_seconds": 0.776
  },
  {
    "tool": "probe",
    "calls": 376,
    "error": 3,
    "avg_duration_seconds": 0.452
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 365,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 364,
    "error": 2,
    "avg_duration_seconds": 3.208
  },
  {
    "tool": "worktree_guard",
    "calls": 341,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 286,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
