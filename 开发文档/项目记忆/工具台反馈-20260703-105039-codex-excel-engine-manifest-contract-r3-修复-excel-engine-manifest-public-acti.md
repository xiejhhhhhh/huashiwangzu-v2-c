---
name: "工具台反馈-20260703-105039-codex-excel-engine-manifest-contract-r3-修复 excel-engine manifest public_acti"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-excel-engine-manifest-contract-r3"
created: "2026-07-03T10:50:39.586678+00:00"
---

# MCP 使用反馈

## 任务

修复 excel-engine manifest public_actions 参数元数据漂移并补 sandbox 契约测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_node 和 capabilities 很快定位到 manifest 与 register_capability 的参数差异。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在多人并行 dirty 场景只能报告全局 outside_allowed，不能区分本 agent 实际 touched files；capabilities 只扫 manifest，不能直接和 live/runtime registry 做参数级 diff。

## 缺少的工具 / 能力

缺 capability_contract_diff(module) 参数级对比工具；缺 touched-files-baseline 或 agent scoped boundary guard。

## 升级建议

为 capabilities 增加 compare_runtime=true 或新增 capability_contract_diff(module)，输出 action/min_role/parameters 的 manifest vs register_capability 差异；finish_task 支持 allowed_prefixes 或 baseline_changed_files。

## 建议移除或合并的工具

无

## 其他备注

sandbox/test_module.py 是手写 main，pytest 会自动发现但官方脚本需要手动把新增测试加入 main；后续新增测试时可提醒。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1069,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 600,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 436,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 413,
    "error": 20,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 412,
    "error": 3,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "call_capability",
    "calls": 411,
    "error": 17,
    "avg_duration_seconds": 0.759
  },
  {
    "tool": "run_test",
    "calls": 376,
    "error": 2,
    "avg_duration_seconds": 3.153
  },
  {
    "tool": "code_impact",
    "calls": 372,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 355,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 300,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
