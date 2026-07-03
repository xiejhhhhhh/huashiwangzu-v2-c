---
name: "工具台反馈-20260703-053459-codex-conductor-收口审查本轮项目记忆/README 边界，补一条 OpenCode 并行"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor"
created: "2026-07-03T05:34:59.952833+00:00"
---

# MCP 使用反馈

## 任务

收口审查本轮项目记忆/README 边界，补一条 OpenCode 并行留痕不删、以终态通知和验收为准的项目记忆。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree_guard/memory_recent 能快速确认记忆和 dirty 状态。

## 本次用到的工具

brief, plan_task, worktree_guard, memory_recent, memory_write, finish_task, mcp_feedback

## 卡点 / 不顺手的地方

共享工作区里其他 worker 持续新增未跟踪记忆，git diff 不显示 untracked，必须额外用 git status 才能解释完整边界。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 能输出 allowed paths 下 tracked diff 与 untracked 新增的分离摘要。

## 升级建议

给项目记忆增加 duplicate/closure 视图：按 agent、title slug、mcp_feedback/task 成对关系聚类，帮助收口时判断留痕而不是污染。

## 建议移除或合并的工具

无

## 其他备注

本次未改 backend/frontend/modules；未删除项目记忆。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 461,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 357,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 258,
    "error": 0,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "run_test",
    "calls": 190,
    "error": 2,
    "avg_duration_seconds": 3.159
  },
  {
    "tool": "worktree_guard",
    "calls": 190,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 163,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "code_impact",
    "calls": 158,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "plan_task",
    "calls": 135,
    "error": 0,
    "avg_duration_seconds": 0.007
  },
  {
    "tool": "probe",
    "calls": 132,
    "error": 0,
    "avg_duration_seconds": 0.475
  }
]
```
