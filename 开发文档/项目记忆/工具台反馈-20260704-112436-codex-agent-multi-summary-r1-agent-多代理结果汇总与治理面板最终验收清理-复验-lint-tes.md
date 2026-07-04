---
name: "工具台反馈-20260704-112436-codex-agent-multi-summary-r1-Agent 多代理结果汇总与治理面板最终验收清理：复验 lint/tes"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-multi-summary-r1"
created: "2026-07-04T11:24:36.980294+00:00"
---

# MCP 使用反馈

## 任务

Agent 多代理结果汇总与治理面板最终验收清理：复验 lint/test/build/capability drift，清理活栈样本 run 12，并确认 list_workflows 空状态。

## 顺畅度

- 评分：5/5
- 体感：整体顺畅，probe、finish_task、memory_write 对最终验收和留痕很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在多并行任务共享工作区中会报告大量 outside_allowed，需要人工区分本任务改动与并行任务 dirty。

## 缺少的工具 / 能力

无

## 升级建议

worktree_guard/finish_task 如能传入并保存开工 baseline，并在收工报告中单独列出“本任务新改动 vs 既有 dirty”，多代理并行时会更省心。

## 建议移除或合并的工具

无

## 其他备注

本次未新增代码，只做主会话最终清理、复验和收工记录。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 138,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "call_capability",
    "calls": 91,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "probe",
    "calls": 91,
    "error": 3,
    "avg_duration_seconds": 0.363
  },
  {
    "tool": "code_explore",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "worktree_guard",
    "calls": 73,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "code_impact",
    "calls": 59,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 59,
    "error": 3,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "brief",
    "calls": 53,
    "error": 0,
    "avg_duration_seconds": 0.734
  },
  {
    "tool": "plan_task",
    "calls": 51,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "run_test",
    "calls": 50,
    "error": 0,
    "avg_duration_seconds": 4.934
  }
]
```
