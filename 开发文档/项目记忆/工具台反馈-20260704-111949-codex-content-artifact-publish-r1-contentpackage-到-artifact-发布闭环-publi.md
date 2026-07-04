---
name: "工具台反馈-20260704-111949-codex-content-artifact-publish-r1-ContentPackage 到 Artifact 发布闭环：publi"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:19:49.567227+00:00"
---

# MCP 使用反馈

## 任务

ContentPackage 到 Artifact 发布闭环：publish 契约、package 发布状态、artifact/file 持久化与活栈验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/probe/run_test/finish_task 组合足够支撑闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, db_schema, probe, call_capability, sql, lint, run_test, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在多并发脏工作区下不容易区分本轮新增与其他 agent 并发改动；lint 工具对目录参数 backend/app/services/content 误报文件不存在，需要用 shell ruff 补跑。

## 缺少的工具 / 能力

希望有一个“本会话 touched files”或“按 patch author/session 汇总”工具，能在并发工作区里更可靠地做边界验收。

## 升级建议

lint 工具支持目录路径递归检查；finish_task 支持 allowed changed subset 与 acknowledged concurrent dirty 分开展示，避免 success 与 boundary_check success=false 混杂。

## 建议移除或合并的工具

无

## 其他备注

子代理审查抓到了 shared editor owner 混用和测试去重清理风险，已修复。

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
    "calls": 88,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "code_explore",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "probe",
    "calls": 73,
    "error": 3,
    "avg_duration_seconds": 0.38
  },
  {
    "tool": "worktree_guard",
    "calls": 70,
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
    "calls": 54,
    "error": 3,
    "avg_duration_seconds": 0.031
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
    "tool": "run_test",
    "calls": 48,
    "error": 0,
    "avg_duration_seconds": 4.916
  }
]
```
