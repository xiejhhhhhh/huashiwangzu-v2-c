---
name: "工具台反馈-20260703-202436-codex-agent-capability-audit-复核并验收 AI Agent 能力上限与成熟工作台对标调研报告"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-capability-audit"
created: "2026-07-03T20:24:36.038525+00:00"
---

# MCP 使用反馈

## 任务

复核并验收 AI Agent 能力上限与成熟工作台对标调研报告

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph、routes/capabilities 和活系统 probe 能快速复现报告关键证据。

## 本次用到的工具

brief, plan_task, worktree_guard, memory_search, code_explore, capabilities, routes, db_schema, probe, call_capability, tail_log, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在大量并行未提交文件存在时输出很长，做只读复核时需要手动建立 baseline 避免误判边界。

## 缺少的工具 / 能力

希望 finish_task/worktree_guard 支持一键使用当前 dirty 作为 named baseline，便于只读验收已有并行产物。

## 升级建议

可增加 report_checklist 工具：输入调研信和报告路径，自动核对章节、执行信数量、只读边界声明、验收标准覆盖情况。

## 建议移除或合并的工具

无

## 其他备注

本轮没有改源码；子代理只读复核后已关闭。

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
    "calls": 683,
    "error": 8,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "lint",
    "calls": 675,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "code_explore",
    "calls": 674,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 587,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 539,
    "error": 18,
    "avg_duration_seconds": 0.652
  },
  {
    "tool": "worktree_guard",
    "calls": 531,
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
    "calls": 481,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 435,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
