---
name: "工具台反馈-20260703-202204-codex-agent-capability-audit-AI Agent 能力上限与成熟工作台对标只读调研"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-capability-audit"
created: "2026-07-03T20:22:04.998064+00:00"
---

# MCP 使用反馈

## 任务

AI Agent 能力上限与成熟工作台对标只读调研

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/routes/capabilities/db_schema/probe/call_capability 对调研证据收集很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, memory_search, code_explore, code_node, routes, capabilities, db_schema, probe, call_capability, tail_log, agent_board_claim, agent_board_heartbeat, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在并行任务大量 dirty 的场景下如果没有提前传入 baseline，会把外部改动全部算作本轮越界，报告类任务收工解释成本较高。

## 缺少的工具 / 能力

缺少一个“只读调研报告收工”模式：可声明本轮仅允许新增指定报告文件和 memory/feedback，自动把开工前 dirty 当 baseline。

## 升级建议

建议 plan_task 返回可复制的 baseline_status_json 或提供 claim 后自动记录 baseline；finish_task 支持 report_only=true，默认不要求 lint/test，并专门展示本轮新增文件。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1443,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "probe",
    "calls": 680,
    "error": 8,
    "avg_duration_seconds": 0.442
  },
  {
    "tool": "lint",
    "calls": 675,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "code_explore",
    "calls": 672,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 587,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 538,
    "error": 18,
    "avg_duration_seconds": 0.652
  },
  {
    "tool": "worktree_guard",
    "calls": 529,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 487,
    "error": 3,
    "avg_duration_seconds": 4.456
  },
  {
    "tool": "code_impact",
    "calls": 478,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 433,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
