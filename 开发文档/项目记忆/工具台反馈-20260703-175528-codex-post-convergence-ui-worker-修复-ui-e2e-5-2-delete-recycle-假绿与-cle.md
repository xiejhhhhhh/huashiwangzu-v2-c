---
name: "工具台反馈-20260703-175528-codex-post-convergence-ui-worker-修复 UI e2e 5.2 delete/recycle 假绿与 cle"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-post-convergence-ui-worker"
created: "2026-07-03T17:55:28.393172+00:00"
---

# MCP 使用反馈

## 任务

修复 UI e2e 5.2 delete/recycle 假绿与 cleanup 清理路径

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_node 很快给出了测试文件全貌，routes 明确了 recycle restore/delete-permanently 的请求契约。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

并行 worker 修改导致 worktree_guard/finish_task 报 outside allowed，需要人工区分这些 dirty 是并行任务而非本轮越界。

## 缺少的工具 / 能力

无

## 升级建议

worktree_guard 若支持“并行任务允许的外部 dirty 只读确认/ack”参数，会更适合多代理 post-convergence repair。

## 建议移除或合并的工具

无

## 其他备注

本轮只修改 frontend/tests/ui-e2e.spec.mjs，未提交。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1247,
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
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 554,
    "error": 8,
    "avg_duration_seconds": 0.453
  },
  {
    "tool": "code_explore",
    "calls": 526,
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
    "tool": "code_impact",
    "calls": 440,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 439,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "db_schema",
    "calls": 368,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
