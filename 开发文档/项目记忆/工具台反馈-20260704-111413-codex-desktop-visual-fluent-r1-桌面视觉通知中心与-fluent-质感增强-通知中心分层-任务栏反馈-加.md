---
name: "工具台反馈-20260704-111413-codex-desktop-visual-fluent-r1-桌面视觉通知中心与 Fluent 质感增强：通知中心分层、任务栏反馈、加"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-visual-fluent-r1"
created: "2026-07-04T11:14:13.954567+00:00"
---

# MCP 使用反馈

## 任务

桌面视觉通知中心与 Fluent 质感增强：通知中心分层、任务栏反馈、加载/空/错误态和最小 Playwright mock 测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和工具台能快速确认影响面；worktree_guard 能准确暴露并行任务 dirty。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

同一工作区并行任务产生大量 dirty，finish_task/guard 会把非本任务文件一起报红，需要人工按任务归属解读。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 支持“本轮 touched files”或 agent-owned file manifest，便于并行任务下区分本任务与其他任务改动。

## 升级建议

增加按 git diff pathspec + untracked pathspec 的边界报告模式，或者允许记录开工时 clean 后的 agent-owned edit ledger。

## 建议移除或合并的工具

无

## 其他备注

本次前端构建和新增 Playwright mock 测试均通过；未使用后端 probe，因为任务为前端视觉且未改 API。

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
    "tool": "code_explore",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "call_capability",
    "calls": 82,
    "error": 5,
    "avg_duration_seconds": 0.293
  },
  {
    "tool": "worktree_guard",
    "calls": 69,
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
    "tool": "probe",
    "calls": 56,
    "error": 2,
    "avg_duration_seconds": 0.411
  },
  {
    "tool": "brief",
    "calls": 52,
    "error": 0,
    "avg_duration_seconds": 0.733
  },
  {
    "tool": "plan_task",
    "calls": 50,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "sql",
    "calls": 48,
    "error": 3,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 45,
    "error": 0,
    "avg_duration_seconds": 4.795
  }
]
```
