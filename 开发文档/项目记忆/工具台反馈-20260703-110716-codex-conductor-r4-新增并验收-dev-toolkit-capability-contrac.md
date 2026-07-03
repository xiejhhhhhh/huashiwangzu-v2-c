---
name: "工具台反馈-20260703-110716-codex-conductor-r4-新增并验收 dev_toolkit capability_contrac"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-r4"
created: "2026-07-03T11:07:16.849747+00:00"
---

# MCP 使用反馈

## 任务

新增并验收 dev_toolkit capability_contract_diff 契约漂移扫描工具。

## 顺畅度

- 评分：4/5
- 体感：brief/plan_task/worktree_guard/finish_task 串联顺畅，适合主会话做验收闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, finish_task, memory_write, mcp_feedback, codegraph CLI

## 卡点 / 不顺手的地方

finish_task 只能给模板，不会自动按模板写 memory，需要主会话再手动调用 memory_write。

## 缺少的工具 / 能力

希望 capability_contract_diff 新工具在 MCP 重启后可直接暴露，并可被 release_gate 选择性调用。

## 升级建议

后续可把 contract diff 的已知动态注册白名单、模块过滤、strict/non-strict 策略接入 release_gate。

## 建议移除或合并的工具

无

## 其他备注

这是为了把后续 manifest/runtime 漂移从人工发现改为可重复扫描。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1102,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 612,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 445,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 442,
    "error": 5,
    "avg_duration_seconds": 0.444
  },
  {
    "tool": "sql",
    "calls": 441,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 430,
    "error": 17,
    "avg_duration_seconds": 0.737
  },
  {
    "tool": "run_test",
    "calls": 393,
    "error": 2,
    "avg_duration_seconds": 3.229
  },
  {
    "tool": "code_impact",
    "calls": 386,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 368,
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
