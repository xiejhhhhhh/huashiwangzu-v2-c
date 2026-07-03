---
name: "工具台反馈-20260703-110212-codex-douyin-delivery-flow-reachability-r3-修复 douyin-delivery 完整投放链不可达：收敛产品定位为内"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-douyin-delivery-flow-reachability-r3"
created: "2026-07-03T11:02:12.281376+00:00"
---

# MCP 使用反馈

## 任务

修复 douyin-delivery 完整投放链不可达：收敛产品定位为内容/计划/交接助手，补 create_delivery_task handoff/dry_run 状态推进闭环和外部 adapter fail-closed。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/guard/codegraph/routes/capabilities/probe/run_test/lint 能覆盖从定位到活栈验收的主链路。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, call_capability, run_test, lint, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 只按全工作区 dirty 判断边界，遇到并发 agent 外部改动时会整体 success=false，无法区分本 agent 实际修改范围。

## 缺少的工具 / 能力

缺少基于开工快照的 agent-local boundary diff 工具；当前只能人工说明并发 dirty。

## 升级建议

给 plan_task/worktree_guard 生成一个 baseline token，finish_task 可基于 baseline 区分本轮新增改动与既有/并发改动。

## 建议移除或合并的工具

无

## 其他备注

活栈验证包含 create_delivery_task、status、external adapter failure、cleanup；测试数据已按 marker 清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1100,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 611,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 444,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 440,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 435,
    "error": 5,
    "avg_duration_seconds": 0.447
  },
  {
    "tool": "call_capability",
    "calls": 420,
    "error": 17,
    "avg_duration_seconds": 0.748
  },
  {
    "tool": "run_test",
    "calls": 390,
    "error": 2,
    "avg_duration_seconds": 3.162
  },
  {
    "tool": "code_impact",
    "calls": 385,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 366,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 316,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
