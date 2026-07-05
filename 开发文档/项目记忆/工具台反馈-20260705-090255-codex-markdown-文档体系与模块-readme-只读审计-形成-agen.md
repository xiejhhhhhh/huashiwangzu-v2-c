---
name: "工具台反馈-20260705-090255-codex-Markdown 文档体系与模块 README 只读审计，形成 Agen"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-05T09:02:55.483451+00:00"
---

# MCP 使用反馈

## 任务

Markdown 文档体系与模块 README 只读审计，形成 Agent 工业化文档瘦身方案

## 顺畅度

- 评分：4/5
- 体感：工具台整体顺畅，brief/plan_task/worktree_guard/code_explore/capability_contract_diff/module_sandbox_matrix/release_gate 能快速给出文档与代码一致性证据。

## 本次用到的工具

brief, plan_task, worktree_guard, sanity_check, tail_log, code_explore, capabilities, routes, module_sandbox_matrix, capability_contract_diff, db_schema, release_gate, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

release_gate preflight 输出巨大且会报告与开工 worktree_guard 不一致的 dirty 状态，需要更清晰地区分工具运行前后新增变更、外部并发变更和本工具产生的临时变更；tail_log 空输出信息量低。

## 缺少的工具 / 能力

缺少专门的 markdown_inventory/doc_drift 工具：自动统计 MD 行数、流水账密度、README 与 manifest/capability/sandbox 的陈述漂移，并生成可应用的文档瘦身 patch 计划。

## 升级建议

新增 docs_audit 工具，输出：入口文档清单、历史噪音占比、过期陈述候选、模块 README 能力表与 manifest 差异、建议归档路径；release_gate 可增加 compact=true 参数减少超长 JSON。

## 建议移除或合并的工具

无。

## 其他备注

本轮主要依靠 subagent 扫描 Markdown 和 MCP 契约工具交叉验证，适合沉淀为标准文档治理工作流。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.143
  },
  {
    "tool": "probe",
    "calls": 81,
    "error": 3,
    "avg_duration_seconds": 0.268
  },
  {
    "tool": "run_test",
    "calls": 67,
    "error": 0,
    "avg_duration_seconds": 3.117
  },
  {
    "tool": "code_impact",
    "calls": 46,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 40,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "sql",
    "calls": 37,
    "error": 6,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "lint",
    "calls": 32,
    "error": 0,
    "avg_duration_seconds": 0.086
  },
  {
    "tool": "call_capability",
    "calls": 28,
    "error": 0,
    "avg_duration_seconds": 0.524
  },
  {
    "tool": "code_explore",
    "calls": 25,
    "error": 1,
    "avg_duration_seconds": 0.347
  },
  {
    "tool": "finish_task",
    "calls": 24,
    "error": 0,
    "avg_duration_seconds": 1.017
  }
]
```
