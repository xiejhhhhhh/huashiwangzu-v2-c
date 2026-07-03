---
name: "工具台反馈-20260703-101646-profile-evolve-governance-fix-r3-修复 profile_evolve 债务治理口径：parse JSON "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "profile-evolve-governance-fix-r3"
created: "2026-07-03T10:16:46.004571+00:00"
---

# MCP 使用反馈

## 任务

修复 profile_evolve 债务治理口径：parse JSON 失败改 manual_review；completed semantic failure 纳入 audit/governance 只读人工复核统计；补测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/CodeGraph/lint/run_test/finish_task 串起来很快定位并验证。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, db_schema, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 在多人并行脏工作区会整体失败，需要额外用目标文件 diff 解释哪些是外部脏状态；probe 命中常驻旧进程，无法直接证明未重启的新字段。

## 缺少的工具 / 能力

无

## 升级建议

worktree_guard/finish_task 可支持 allowed_prefixes 参数并区分本次触碰文件与既有脏文件；probe 可显示服务进程代码加载时间或 git mtime，帮助判断是否需要重启。

## 建议移除或合并的工具

无

## 其他备注

未 commit/push；未重启后端以避免打断并行代理。

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
    "calls": 592,
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
    "calls": 362,
    "error": 2,
    "avg_duration_seconds": 3.222
  },
  {
    "tool": "worktree_guard",
    "calls": 340,
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
