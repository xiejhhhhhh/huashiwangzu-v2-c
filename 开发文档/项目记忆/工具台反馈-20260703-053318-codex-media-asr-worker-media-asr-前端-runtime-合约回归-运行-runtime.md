---
name: "工具台反馈-20260703-053318-codex-media-asr-worker-media-asr 前端/runtime 合约回归：运行 runtime"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-media-asr-worker"
created: "2026-07-03T05:33:18.404767+00:00"
---

# MCP 使用反馈

## 任务

media-asr 前端/runtime 合约回归：运行 runtime drift、vue-tsc，审查并补严 unknown 类型守卫。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree_guard 能快速确认大工作区和边界。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

code_explore 没有准确展开 media-asr 目标文件，最后回退到 codegraph node CLI；plan_task 的模块边界不支持用户额外允许 frontend/scripts/check-runtime-drift.js 这种混合边界，需要人工覆盖。

## 缺少的工具 / 能力

当前暴露工具里没有 finish_task/code_node/code_impact/routes/capabilities 的直接 MCP callable，部分 required_evidence 只能用 CLI 或 plan_task 预采证据补足。

## 升级建议

plan_task 增加 allowed_prefixes 参数；tool_search 暴露 code_node/code_impact/routes/capabilities/finish_task，减少 CLI 回退。

## 建议移除或合并的工具

无

## 其他备注

本轮同时按用户要求补起两个后台 Codex worker：dev_toolkit worker 与 backend foundation worker。

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
    "calls": 341,
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
    "calls": 253,
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
    "calls": 189,
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
    "calls": 156,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "plan_task",
    "calls": 134,
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
