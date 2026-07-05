---
name: "工具台反馈-20260705-070354-codex-Agent/Knowledge/Memory 前端入口拆分与状态组合清理"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-05T07:03:54.550640+00:00"
---

# MCP 使用反馈

## 任务

Agent/Knowledge/Memory 前端入口拆分与状态组合清理，提交 1c26f0ec。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；brief/plan_task/worktree_guard/codegraph/routes/capabilities 能快速锁定范围和契约。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, finish_task, memory_write, mcp_feedback, mailbox_create_delivery_bundle, mailbox_check_delivery_bundle

## 卡点 / 不顺手的地方

worktree_guard 很好地发现了并行外部改动，但无法把“本提交范围干净”和“全工作区有他人改动”同时表达为通过，需要人工在风险里说明。

## 缺少的工具 / 能力

希望有按 staged diff 做边界验收的工具，适合并行 agent 场景。

## 升级建议

finish_task 可增加 staged_only=true 或 commit_hash 参数，区分已提交任务范围与工作区其它未暂存改动。

## 建议移除或合并的工具

无

## 其他备注

Playwright 全量跑到文件删除/回收流程时因 Session expired 失败，构建与目标模块打开场景通过。

## 当前工具热度快照

```json
[
  {
    "tool": "probe",
    "calls": 58,
    "error": 3,
    "avg_duration_seconds": 0.258
  },
  {
    "tool": "run_test",
    "calls": 51,
    "error": 0,
    "avg_duration_seconds": 2.735
  },
  {
    "tool": "code_node",
    "calls": 27,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "lint",
    "calls": 26,
    "error": 0,
    "avg_duration_seconds": 0.091
  },
  {
    "tool": "worktree_guard",
    "calls": 25,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 24,
    "error": 3,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 19,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "finish_task",
    "calls": 15,
    "error": 0,
    "avg_duration_seconds": 1.183
  },
  {
    "tool": "release_gate",
    "calls": 15,
    "error": 0,
    "avg_duration_seconds": 23.544
  },
  {
    "tool": "test_data_pollution_audit",
    "calls": 14,
    "error": 0,
    "avg_duration_seconds": 0.034
  }
]
```
