---
name: "工具台反馈-20260703-051951-opencode-r1-devtool-升级项目工具台 MCP 健壮性: 修复 insight_tools 自检"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode-r1-devtool"
created: "2026-07-03T05:19:51.275078+00:00"
---

# MCP 使用反馈

## 任务

升级项目工具台 MCP 健壮性: 修复 insight_tools 自检盲区 + opencode 公共模块提取 + PTY 文件拆分

## 顺畅度

- 评分：4/5
- 体感：整体顺畅。codegraph 大幅节省了逐文件阅读的时间，quick_fix_preview/patch 精确替换减少了出错可能。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore (codegraph x4), code_node, read, edit, batch_quick_fix_preview/apply, lint, run_test, memory_write, mcp_feedback, finish_task

## 卡点 / 不顺手的地方

codegraph explore 有 2 calls budget，对大型项目不够用，被迫回退 read。edit 工具对 multiline 替换敏感，需要精确匹配空白。

## 缺少的工具 / 能力

无

## 升级建议

codegraph explore 的 budget 可以根据项目大小动态调整。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 447,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 341,
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
    "calls": 240,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 190,
    "error": 2,
    "avg_duration_seconds": 3.159
  },
  {
    "tool": "worktree_guard",
    "calls": 179,
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
    "calls": 148,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "probe",
    "calls": 130,
    "error": 0,
    "avg_duration_seconds": 0.477
  },
  {
    "tool": "plan_task",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
