---
name: "工具台反馈-20260703-103832-frontend-runtime-contract-audit-r3-只读审计 frontend/src 与 modules/*/runtim"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "frontend-runtime-contract-audit-r3"
created: "2026-07-03T10:38:32.267528+00:00"
---

# MCP 使用反馈

## 任务

只读审计 frontend/src 与 modules/*/runtime/index.ts 的前端 runtime/后端能力契约漂移

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，routes/capabilities/code_explore 对确认 /api/modules/call 与参数字段很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, capabilities, routes, tail_log, memory_write, shell rg/node/python

## 卡点 / 不顺手的地方

capabilities 输出很长且被截断，不适合直接做全量 diff；需要另写 AST 脚本对 manifest 与 register_capability 做结构化对比。

## 缺少的工具 / 能力

建议新增 capability_contract_diff(module?)：直接比较 manifest public_actions 与运行时 register_capability 的 action/parameters/min_role，并标注必填/可选差异。

## 升级建议

capabilities 可增加 compact/json-lines 模式，或按 module 分页，避免大仓全量输出截断。

## 建议移除或合并的工具

无

## 其他备注

本次未改产品代码；memory_write 按要求落盘。

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
    "calls": 595,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 417,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 398,
    "error": 17,
    "avg_duration_seconds": 0.774
  },
  {
    "tool": "probe",
    "calls": 379,
    "error": 3,
    "avg_duration_seconds": 0.451
  },
  {
    "tool": "run_test",
    "calls": 370,
    "error": 2,
    "avg_duration_seconds": 3.189
  },
  {
    "tool": "code_impact",
    "calls": 367,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 344,
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
