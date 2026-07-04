---
name: "工具台反馈-20260704-134047-codex-workflow-seed-governance-落地 Agent workflow demo seed/cleanup、"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-workflow-seed-governance"
created: "2026-07-04T13:40:47.584240+00:00"
---

# MCP 使用反馈

## 任务

落地 Agent workflow demo seed/cleanup、治理 summary、列表筛选与详情动作，并完成活栈 seed-cleanup 验证

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 release_gate 对定位影响面与发现 live capability drift 很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, routes, capabilities, lint, run_test, release_gate, call_capability, sql, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在大量并行 dirty 和中文路径场景下较难表达“本轮允许范围 + 外部并行基线”，容易把非本轮变更算成越界。

## 缺少的工具 / 能力

希望有一个基于开工快照自动生成 baseline_paths 的轻量 token，例如 worktree_guard 返回可直接传 finish_task 的 baseline_id。

## 升级建议

release_gate 发现 capability drift 后可以提示“是否需要重启后端”以及列出新增 source capability 对应文件，减少人工判断。

## 建议移除或合并的工具

无

## 其他备注

本次按规则重启后端后 drift 清零；finish_task 仍如实报告外部 dirty，最终说明中需人工区分。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 453,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "code_explore",
    "calls": 281,
    "error": 0,
    "avg_duration_seconds": 0.341
  },
  {
    "tool": "worktree_guard",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 169,
    "error": 4,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "brief",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.765
  },
  {
    "tool": "plan_task",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "code_impact",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "call_capability",
    "calls": 119,
    "error": 5,
    "avg_duration_seconds": 0.297
  },
  {
    "tool": "sql",
    "calls": 116,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "routes",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.051
  }
]
```
