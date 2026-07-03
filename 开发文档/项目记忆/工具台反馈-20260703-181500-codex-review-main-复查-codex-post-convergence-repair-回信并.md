---
name: "工具台反馈-20260703-181500-codex-review-main-复查 Codex post-convergence repair 回信并"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-review-main"
created: "2026-07-03T18:15:00.516889+00:00"
---

# MCP 使用反馈

## 任务

复查 Codex post-convergence repair 回信并生成下一封补漏/收尾交付信

## 顺畅度

- 评分：4/5
- 体感：本次 MCP 可用，tool_job_submit/status 正常，适合验证长任务 job 化。

## 本次用到的工具

brief,plan_task,worktree_guard,code_explore,tail_log,_snap_diff,tool_job_submit,tool_job_status,tool_job_notifications,finish_task,memory_write

## 卡点 / 不顺手的地方

code_explore 对精确新文件检索仍会混入较多无关符号，需要配合 Read 定点确认。

## 缺少的工具 / 能力

希望有直接对当前 diff 做结构化审计的工具，按文件列出新增函数/风险点。

## 升级建议

tool_job_status 对 PASS_WITH_DEBT 的 success 字段建议区分 command_success 与 clean_success/release_safe，避免调用方误判。

## 建议移除或合并的工具

无

## 其他备注

本轮未改代码，仅复查并产出下一封 Codex 补漏信。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1290,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "lint",
    "calls": 650,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 567,
    "error": 8,
    "avg_duration_seconds": 0.451
  },
  {
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 546,
    "error": 0,
    "avg_duration_seconds": 0.326
  },
  {
    "tool": "call_capability",
    "calls": 495,
    "error": 17,
    "avg_duration_seconds": 0.684
  },
  {
    "tool": "run_test",
    "calls": 450,
    "error": 3,
    "avg_duration_seconds": 4.591
  },
  {
    "tool": "worktree_guard",
    "calls": 448,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 444,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 368,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
