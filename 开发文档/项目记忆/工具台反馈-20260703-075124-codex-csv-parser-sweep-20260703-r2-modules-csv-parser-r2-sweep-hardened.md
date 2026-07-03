---
name: "工具台反馈-20260703-075124-codex-csv-parser-sweep-20260703-r2-modules/csv-parser r2 sweep hardened"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-csv-parser-sweep-20260703-r2"
created: "2026-07-03T07:51:24.332624+00:00"
---

# MCP 使用反馈

## 任务

modules/csv-parser r2 sweep hardened CSV parser boundaries and sandbox coverage

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/lint/probe/call_capability/run_test 串起来能覆盖本次模块扫雷。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, sql, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的 module_key 边界不支持额外允许 开发文档/项目记忆，且会被既有其他 agent 脏工作区影响而整体 success:false；需要人工解释基线。

## 缺少的工具 / 能力

缺少一个“按本 agent 本次触达文件”做边界验收的工具，最好能接收 allowed_prefixes 并排除开工前基线。

## 升级建议

worktree_guard/finish_task 可以支持 baseline token：开工记录一份 dirty 快照，收工只判新增越界；同时 finish_task 增加 allowed_prefixes 参数。

## 建议移除或合并的工具

无

## 其他备注

未做上传正向 probe，因为会写 data/uploads，违反本任务边界；改用现有库查询确认无 CSV/TSV 可复用，并验证 invalid capability 统一失败语义。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 792,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 526,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 339,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 323,
    "error": 17,
    "avg_duration_seconds": 0.713
  },
  {
    "tool": "sql",
    "calls": 304,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 296,
    "error": 2,
    "avg_duration_seconds": 3.545
  },
  {
    "tool": "worktree_guard",
    "calls": 291,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 282,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 281,
    "error": 2,
    "avg_duration_seconds": 0.483
  },
  {
    "tool": "db_schema",
    "calls": 232,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
