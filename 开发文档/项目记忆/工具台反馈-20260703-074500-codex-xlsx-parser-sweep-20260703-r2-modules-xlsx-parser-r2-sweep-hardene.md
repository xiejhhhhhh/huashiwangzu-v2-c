---
name: "工具台反馈-20260703-074500-codex-xlsx-parser-sweep-20260703-r2-modules/xlsx-parser r2 sweep hardene"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-xlsx-parser-sweep-20260703-r2"
created: "2026-07-03T07:45:00.441817+00:00"
---

# MCP 使用反馈

## 任务

modules/xlsx-parser r2 sweep hardened parser core, error semantics, sandbox real regression coverage, manifest/docs alignment

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/lint/run_test/probe 能覆盖主流程。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在并发脏工作区下只能给全局失败，需要人工区分本任务 diff；run_test 默认 pytest，脚本型 sandbox 若无 pytest test 会先报 0 tests。

## 缺少的工具 / 能力

缺一个只看本 agent 新增 diff 的边界检查，或支持 allowed_prefixes 包含项目记忆并排除既有 dirty baseline 的 finish_task 模式。

## 升级建议

plan_task 可以把脚本型 sandbox 自动建议补 pytest 入口；call_capability 可提示当前后端代码是否热加载/重启时间，帮助判断活栈是否加载新模块。

## 建议移除或合并的工具

无

## 其他备注

未重启常驻后端，避免写 backend/logs 等越界产物；通过直接导入验证新 router 错误语义。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 762,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 523,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 332,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 317,
    "error": 17,
    "avg_duration_seconds": 0.721
  },
  {
    "tool": "sql",
    "calls": 303,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 294,
    "error": 2,
    "avg_duration_seconds": 3.564
  },
  {
    "tool": "worktree_guard",
    "calls": 284,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 272,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 271,
    "error": 2,
    "avg_duration_seconds": 0.49
  },
  {
    "tool": "db_schema",
    "calls": 228,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
