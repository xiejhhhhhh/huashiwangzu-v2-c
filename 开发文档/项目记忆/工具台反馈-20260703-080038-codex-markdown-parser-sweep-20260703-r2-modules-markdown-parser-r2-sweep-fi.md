---
name: "工具台反馈-20260703-080038-codex-markdown-parser-sweep-20260703-r2-modules/markdown-parser r2 sweep: fi"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-markdown-parser-sweep-20260703-r2"
created: "2026-07-03T08:00:38.348279+00:00"
---

# MCP 使用反馈

## 任务

modules/markdown-parser r2 sweep: fixed file_id validation, parser code fence/table handling, sandbox production parser coverage, and verified lint/tests.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph 和 run_test 对定位与验证很有用。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在并行 agent 大量 dirty 文件时会整体报越界，需要人工区分本 agent diff 与外部基线。活栈后端未热加载模块代码，探针会命中旧逻辑。

## 缺少的工具 / 能力

希望有按 agent 允许路径+本次修改基线的 boundary_diff 工具；希望有安全的模块热重载/单模块 reload probe。

## 升级建议

finish_task 可支持 baseline_changed_files 参数，忽略开工时已有 dirty；probe/call_capability 可返回 backend build/reload timestamp 或模块代码 mtime，帮助判断热加载状态。

## 建议移除或合并的工具

无

## 其他备注

未重启共享后端以避免影响并行 image/text/csv/pptx/docx/xlsx 等 agent。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 830,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 541,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "code_explore",
    "calls": 347,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 342,
    "error": 17,
    "avg_duration_seconds": 0.688
  },
  {
    "tool": "probe",
    "calls": 308,
    "error": 3,
    "avg_duration_seconds": 0.479
  },
  {
    "tool": "sql",
    "calls": 307,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 303,
    "error": 2,
    "avg_duration_seconds": 3.477
  },
  {
    "tool": "worktree_guard",
    "calls": 296,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 293,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 236,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
