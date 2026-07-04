---
name: "工具台反馈-20260704-125556-codex-lane-e-releasegate-audit-Lane E ReleaseGate/测试矩阵/文档审计，只读确认 bl"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-lane-e-releasegate-audit"
created: "2026-07-04T12:55:56.557100+00:00"
---

# MCP 使用反馈

## 任务

Lane E ReleaseGate/测试矩阵/文档审计，只读确认 blocker/debt 根因和 README 批量补齐策略。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，release_gate 与 module_sandbox_matrix 直接给出了高信号机器结果。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, release_gate, module_sandbox_matrix, tool_job_submit, tool_job_status, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

module_sandbox_matrix 后台 job 的 parsed_result 未摘要 pass/fail/skip/chunk warning，需要手动解析 log 才能得到简短计数。

## 缺少的工具 / 能力

缺少 README acceptance matrix 的 summary-only/patch-plan 工具：希望直接输出 missing README、缺验收小节、建议命令三列表。

## 升级建议

建议 module_sandbox_matrix MCP 返回 summary 字段：total/pass/fail/skip/readme_missing/readme_lacks_acceptance/chunk_warning_modules，并提供 --readme-plan 输出可复制矩阵块。

## 建议移除或合并的工具

无

## 其他备注

本轮未修改源码或 README，仅按项目规则写入记忆与反馈。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.142
  },
  {
    "tool": "code_explore",
    "calls": 231,
    "error": 0,
    "avg_duration_seconds": 0.336
  },
  {
    "tool": "probe",
    "calls": 163,
    "error": 4,
    "avg_duration_seconds": 0.319
  },
  {
    "tool": "worktree_guard",
    "calls": 157,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.757
  },
  {
    "tool": "plan_task",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "sql",
    "calls": 115,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 113,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "code_impact",
    "calls": 109,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "finish_task",
    "calls": 76,
    "error": 0,
    "avg_duration_seconds": 1.834
  }
]
```
