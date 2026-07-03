---
name: "工具台反馈-20260703-070419-codex-codemap-sweep-20260703-r2-codemap sweep r2: 修复索引可信度、空索引假成功、反馈校"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-codemap-sweep-20260703-r2"
created: "2026-07-03T07:04:19.840850+00:00"
---

# MCP 使用反馈

## 任务

codemap sweep r2: 修复索引可信度、空索引假成功、反馈校验、locks.json fail-closed 与验证覆盖。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 capability/probe 能快速定位与验活。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

lint 工具不接受目录路径，只能传文件列表；worktree_guard 在并行 worker 场景会因他人改动整体 success=false，需要人工区分 own diff。

## 缺少的工具 / 能力

缺少按 agent/allowed prefixes 只评估当前新增 diff 的边界摘要；缺少安全的测试反馈记录自动清理工具。

## 升级建议

lint 支持目录递归；worktree_guard 增加 only_allowed_summary 或 ignore_existing_dirty；call_capability 可更清晰展示内层 success 与 HTTP 422 的关系。

## 建议移除或合并的工具

无

## 其他备注

本次未重启后端，活系统验证使用常驻栈；测试数据锁已释放，空反馈校验未写入 DB。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 690,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 486,
    "error": 0,
    "avg_duration_seconds": 0.022
  },
  {
    "tool": "code_explore",
    "calls": 314,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 296,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 272,
    "error": 2,
    "avg_duration_seconds": 3.75
  },
  {
    "tool": "worktree_guard",
    "calls": 251,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "call_capability",
    "calls": 234,
    "error": 12,
    "avg_duration_seconds": 0.646
  },
  {
    "tool": "db_schema",
    "calls": 205,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 193,
    "error": 2,
    "avg_duration_seconds": 0.447
  }
]
```
