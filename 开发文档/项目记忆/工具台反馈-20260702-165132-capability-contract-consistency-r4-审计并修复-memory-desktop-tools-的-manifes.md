---
name: "工具台反馈-20260702-165132-capability-contract-consistency-r4-审计并修复 memory、desktop-tools 的 manifes"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "capability-contract-consistency-r4"
created: "2026-07-02T16:51:32.400972+00:00"
---

# MCP 使用反馈

## 任务

审计并修复 memory、desktop-tools 的 manifest public_actions 与 register_capability 契约漂移。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/capabilities/routes/run_test/probe 能串起来完成闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, run_test, lint, probe, call_capability, sql, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task/run_test 混合 backend/tests 与 modules/*/sandbox 目标时会错误切换 rootdir，导致路径归一化假失败；lint 工具不支持一次传多个路径。

## 缺少的工具 / 能力

缺一个 manifest-vs-register 契约扫描工具，可按模块输出 action/min_role/参数漂移与重复注册。

## 升级建议

把本次 AST+manifest 比对沉淀成 dev_toolkit 工具或 release_gate 子检查；scan-register 后可提供 app registry 与 manifest 快照差异摘要。

## 建议移除或合并的工具

无

## 其他备注

活系统 DB app registry 是 manifest 快照，代码改 manifest 后需 scan-register 或重启触发 sync_apps_from_manifest；本次已用标准接口同步。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 384,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 269,
    "error": 0,
    "avg_duration_seconds": 0.016
  },
  {
    "tool": "sql",
    "calls": 188,
    "error": 8,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_explore",
    "calls": 185,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "code_impact",
    "calls": 123,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 2.258
  },
  {
    "tool": "db_schema",
    "calls": 114,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 97,
    "error": 0,
    "avg_duration_seconds": 0.539
  },
  {
    "tool": "plan_task",
    "calls": 84,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
