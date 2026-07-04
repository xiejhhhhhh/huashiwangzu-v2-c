---
name: "工具台反馈-20260704-121721-codex-artifact-desktop-entry-r1-Artifact 桌面可见与下载入口闭环最终验收：复核执行信、CodeG"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-artifact-desktop-entry-r1"
created: "2026-07-04T12:17:21.396071+00:00"
---

# MCP 使用反馈

## 任务

Artifact 桌面可见与下载入口闭环最终验收：复核执行信、CodeGraph 影响面、跑前端 build、后端 pytest、Playwright 活栈、边界守卫、污染检查并写收口文档。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/worktree_guard/finish_task 能把复杂脏工作区里的本任务边界收住。

## 本次用到的工具

brief, plan_task, code_explore, code_node, code_impact, worktree_guard, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 目前不能直接传额外 forbidden_prefixes，最终输出里的 forbidden 只含默认项；需要单独跑 worktree_guard 记录执行信禁止路径 new_forbidden_hit_count=0。

## 缺少的工具 / 能力

希望 finish_task 支持 forbidden_prefixes 参数，并在 summary 中明确显示 custom forbidden 的 baseline/new 命中。

## 升级建议

finish_task 可接受已跑命令的 stdout 摘要字段，并支持把 worktree_guard 的独立结果引用进最终报告。

## 建议移除或合并的工具

无

## 其他备注

本轮曾因目标从视觉任务切换到 Artifact 任务，需要关闭刚派出的视觉子代理；工具本身可控。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 326,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 194,
    "error": 0,
    "avg_duration_seconds": 0.337
  },
  {
    "tool": "probe",
    "calls": 145,
    "error": 4,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "worktree_guard",
    "calls": 135,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 106,
    "error": 0,
    "avg_duration_seconds": 0.752
  },
  {
    "tool": "plan_task",
    "calls": 105,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "call_capability",
    "calls": 104,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "code_impact",
    "calls": 102,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "finish_task",
    "calls": 67,
    "error": 0,
    "avg_duration_seconds": 1.514
  }
]
```
