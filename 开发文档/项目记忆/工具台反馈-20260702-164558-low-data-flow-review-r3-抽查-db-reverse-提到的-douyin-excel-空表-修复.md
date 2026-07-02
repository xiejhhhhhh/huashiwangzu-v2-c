---
name: "工具台反馈-20260702-164558-low-data-flow-review-r3-抽查 db_reverse 提到的 douyin/excel 空表，修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "low-data-flow-review-r3"
created: "2026-07-02T16:45:58.804842+00:00"
---

# MCP 使用反馈

## 任务

抽查 db_reverse 提到的 douyin/excel 空表，修复 excel 导入布局不入库并报告 douyin 前端方法错配。

## 顺畅度

- 评分：4/5
- 体感：工具台整体顺畅；通过直接调用 stdio 组件完成 brief/plan/db_reverse/probe/sql/lint/run_test/finish/memory。

## 本次用到的工具

brief, plan_task, worktree_guard, memory_search, db_reverse_audit, codegraph explore/node/impact, capabilities, routes, db_schema, probe, sql, tail_log, lint, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前会话没有原生 MCP 工具按钮，只能用 Python 包装 handler；code_tools handler 签名不统一，第一次少传参数报错。worktree_guard 在并行 dirty 很多时需要额外解释哪些是本任务改动。

## 缺少的工具 / 能力

希望有“本 agent 本轮改动集”或“按开始快照 diff”工具，能把并行 dirty 和本轮改动自动分离。

## 升级建议

给 dev_toolkit 增加统一 local_call CLI/脚本入口，按 tool name + JSON 调用，避免每个组件手写不同 handler 包装。worktree_guard 可支持 baseline snapshot id。

## 建议移除或合并的工具

无

## 其他备注

未重启活栈，避免干扰并行代理；后续需要统一重启后再用 probe 验证 excel open/import 新行为。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 375,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 264,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 182,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "sql",
    "calls": 171,
    "error": 7,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 120,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 112,
    "error": 0,
    "avg_duration_seconds": 2.31
  },
  {
    "tool": "db_schema",
    "calls": 110,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 86,
    "error": 0,
    "avg_duration_seconds": 0.566
  },
  {
    "tool": "plan_task",
    "calls": 83,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
