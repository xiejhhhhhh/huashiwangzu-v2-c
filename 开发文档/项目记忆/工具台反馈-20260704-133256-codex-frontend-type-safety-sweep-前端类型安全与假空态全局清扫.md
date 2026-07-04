---
name: "工具台反馈-20260704-133256-codex-frontend-type-safety-sweep-前端类型安全与假空态全局清扫"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-frontend-type-safety-sweep"
created: "2026-07-04T13:32:56.391823+00:00"
---

# MCP 使用反馈

## 任务

前端类型安全与假空态全局清扫

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和工具台能快速定位 LoadState/ApiErrorInfo 影响点。

## 本次用到的工具

brief
plan_task
worktree_guard
code_explore
code_node
code_impact
finish_task
memory_write
mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在大量并行 dirty 工作区里较难区分本轮改动和其他 agent 改动，需要手动解释。

## 缺少的工具 / 能力

缺少面向前端的 eslint/tsc 精准工具台封装；当前主要依赖 npm build 和 rg。

## 升级建议

finish_task 可支持从开工 worktree_guard 输出自动传递 baseline id，避免长 baseline_paths。增加前端失败态 Playwright 模板生成会更好。

## 建议移除或合并的工具

无

## 其他备注

5 个只读子代理分片审计很有帮助，但其中有子代理按项目规则写了记忆文件，导致 read-only 审计也产生额外项目记忆 dirty。

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
    "calls": 168,
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
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 115,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 114,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "routes",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.051
  }
]
```
