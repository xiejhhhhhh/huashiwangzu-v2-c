---
name: "工具台反馈-20260702-164333-frontend-runtime-review-r3-review and complete interrupted fron"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "frontend-runtime-review-r3"
created: "2026-07-02T16:43:33.990923+00:00"
---

# MCP 使用反馈

## 任务

review and complete interrupted frontend runtime/API consolidation; fixed remaining Excel editor swallowed errors and verified frontend build/scans

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph/guard/finish_task 串联能快速确认边界和影响面。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

code_explore 对自然语言 query 第一轮命中不够准，返回了不少无关模板组件；worktree 里并发/他人改动很多，finish_task 的 dirty 样本会混入非本轮文件。

## 缺少的工具 / 能力

缺少一个能标记“本 agent 本轮实际触碰文件”的轻量工具，用于和已有脏 worktree 区分。

## 升级建议

worktree_guard/finish_task 可支持传入 baseline timestamp 或初始 status snapshot，输出本轮新增/变更文件集合。

## 建议移除或合并的工具

无

## 其他备注

未触碰 backend/knowledge/memory；前端 npm run build 已通过。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 370,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 264,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "sql",
    "calls": 171,
    "error": 7,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 120,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 112,
    "error": 0,
    "avg_duration_seconds": 2.31
  },
  {
    "tool": "db_schema",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 86,
    "error": 0,
    "avg_duration_seconds": 0.566
  },
  {
    "tool": "plan_task",
    "calls": 79,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
