---
name: "工具台反馈-20260703-203230-codex-agent-workflow-runtime-link-Agent workflow runtime link 接入真实对话、工"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-workflow-runtime-link"
created: "2026-07-03T20:32:30.045305+00:00"
---

# MCP 使用反馈

## 任务

Agent workflow runtime link 接入真实对话、工具调用、审批、checkpoint、子 Agent 与验证链路

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/finish_task 把任务边界和验收链路串得很稳。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, capability_contract_diff, probe, call_capability, sql, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在大 dirty 工作区里需要手动整理 baseline_paths；如果能一键从开工 guard 输出生成 baseline token 会更省心。

## 缺少的工具 / 能力

无关键缺失；本次 capability_contract_diff 后加载才可见，但可用。

## 升级建议

建议 finish_task 支持引用某次 worktree_guard 的结果作为 baseline，避免大段路径手填。

## 建议移除或合并的工具

无

## 其他备注

使用 3 个 read-only explorer 子代理并已关闭；活系统探针数据已清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1461,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "code_explore",
    "calls": 684,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 684,
    "error": 8,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "lint",
    "calls": 678,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "sql",
    "calls": 588,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 548,
    "error": 18,
    "avg_duration_seconds": 0.646
  },
  {
    "tool": "worktree_guard",
    "calls": 536,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 495,
    "error": 3,
    "avg_duration_seconds": 4.434
  },
  {
    "tool": "code_impact",
    "calls": 491,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 441,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
