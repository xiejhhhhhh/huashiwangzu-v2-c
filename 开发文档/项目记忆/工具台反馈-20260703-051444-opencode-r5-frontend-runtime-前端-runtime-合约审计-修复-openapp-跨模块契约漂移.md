---
name: "工具台反馈-20260703-051444-opencode-r5-frontend-runtime-前端 Runtime 合约审计：修复 openApp 跨模块契约漂移 +"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode-r5-frontend-runtime"
created: "2026-07-03T05:14:44.362017+00:00"
---

# MCP 使用反馈

## 任务

前端 Runtime 合约审计：修复 openApp 跨模块契约漂移 + 补齐 KNOWN_VARIANTS

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph 查代码快准；vue-tsc 类型检查通过

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, grep, read, edit, quick_fix_patch

## 卡点 / 不顺手的地方

check-runtime-drift.js 第一次跑未发现 office-gen 是预存 drift，需要二次人工确认 diff；vue-tsc -b --noEmit 没有进度输出让人不确定是否在运行

## 缺少的工具 / 能力

全局 TS 类型检查时无进度输出

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
    "calls": 333,
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
    "calls": 234,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 183,
    "error": 1,
    "avg_duration_seconds": 2.774
  },
  {
    "tool": "worktree_guard",
    "calls": 174,
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
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
