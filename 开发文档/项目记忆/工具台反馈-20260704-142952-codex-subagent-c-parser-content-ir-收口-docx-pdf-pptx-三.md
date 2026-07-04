---
name: "工具台反馈-20260704-142952-codex-subagent-c-Parser Content IR 收口：docx/pdf/pptx 三"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-subagent-c"
created: "2026-07-04T14:29:52.209867+00:00"
---

# MCP 使用反馈

## 任务

Parser Content IR 收口：docx/pdf/pptx 三模块输出与 sandbox 验收升级。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 对 parser 和 sandbox 定位很快。

## 本次用到的工具

brief, plan_task, worktree_guard, finish_task, memory_write, mcp_feedback, codegraph CLI

## 卡点 / 不顺手的地方

并行任务期间出现范围外 dirty，worktree_guard 收尾会按新变更报红，需人工结合开工基线判断。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 能直接引用本轮开工快照 ID，自动区分并行新增 dirty。

## 升级建议

给 finish_task 增加 scoped_diff_summary，仅以 allowed_prefixes 汇总本 agent 实际交付，同时单列并行 dirty。

## 建议移除或合并的工具

无

## 其他备注

组合 pytest 多个同名 sandbox/test_module.py 会 import mismatch，分模块单跑通过。

## 当前工具热度快照

```json
[
  {
    "tool": "run_test",
    "calls": 16,
    "error": 0,
    "avg_duration_seconds": 2.858
  },
  {
    "tool": "code_node",
    "calls": 15,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "probe",
    "calls": 15,
    "error": 3,
    "avg_duration_seconds": 0.225
  },
  {
    "tool": "code_impact",
    "calls": 11,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "lint",
    "calls": 8,
    "error": 0,
    "avg_duration_seconds": 0.061
  },
  {
    "tool": "worktree_guard",
    "calls": 8,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "finish_task",
    "calls": 7,
    "error": 0,
    "avg_duration_seconds": 0.308
  },
  {
    "tool": "capabilities",
    "calls": 6,
    "error": 0,
    "avg_duration_seconds": 0.001
  },
  {
    "tool": "tail_log",
    "calls": 4,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "tool_job_status",
    "calls": 3,
    "error": 0,
    "avg_duration_seconds": 0.003
  }
]
```
