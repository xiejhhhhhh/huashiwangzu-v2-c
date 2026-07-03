---
name: "工具台反馈-20260703-101727-content-pipeline-access-fix-r3-修复 content pipeline 权限校验与 get_file_c"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "content-pipeline-access-fix-r3"
created: "2026-07-03T10:17:27.140366+00:00"
---

# MCP 使用反馈

## 任务

修复 content pipeline 权限校验与 get_file_content 假成功语义

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/CodeGraph/lint/run_test 能覆盖主流程。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 对全仓并发脏文件很敏感，需要人工区分本任务 allowed 范围和其他 agent 改动。

## 缺少的工具 / 能力

无

## 升级建议

finish_task 若能接收 allowed_prefixes/forbidden_prefixes 并复用任务边界，会比默认全仓边界更贴合并发任务。

## 建议移除或合并的工具

无

## 其他备注

严格避开了 Copernicus 正在修改的 export_service.py；仅改 pipeline_service.py、content.py、相关测试。

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
