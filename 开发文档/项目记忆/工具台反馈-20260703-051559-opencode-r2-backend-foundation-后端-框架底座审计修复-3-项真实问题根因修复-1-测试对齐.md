---
name: "工具台反馈-20260703-051559-opencode-r2-backend-foundation-后端/框架底座审计修复：3 项真实问题根因修复 + 1 测试对齐"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode-r2-backend-foundation"
created: "2026-07-03T05:15:59.704550+00:00"
---

# MCP 使用反馈

## 任务

后端/框架底座审计修复：3 项真实问题根因修复 + 1 测试对齐

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph 查代码省了很多逐文件读的时间

## 本次用到的工具

brief, plan_task, worktree_guard, codegraph_explore, codegraph_node, lint, probe, run_test, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

edit 工具在多行长字符串替换时需仔细匹配缩进；finish_task 汇总 71 个 dirty 文件时包括了大量非本次改动

## 缺少的工具 / 能力

无

## 升级建议

无

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 335,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 238,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 185,
    "error": 1,
    "avg_duration_seconds": 2.831
  },
  {
    "tool": "worktree_guard",
    "calls": 178,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 162,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "code_impact",
    "calls": 147,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "probe",
    "calls": 127,
    "error": 0,
    "avg_duration_seconds": 0.482
  },
  {
    "tool": "plan_task",
    "calls": 124,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
