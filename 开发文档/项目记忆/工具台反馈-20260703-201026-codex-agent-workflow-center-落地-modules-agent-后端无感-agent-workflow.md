---
name: "工具台反馈-20260703-201026-codex-agent-workflow-center-落地 modules/agent 后端无感 Agent workflow"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-workflow-center"
created: "2026-07-03T20:10:26.947851+00:00"
---

# MCP 使用反馈

## 任务

落地 modules/agent 后端无感 Agent workflow 中枢，并用 5 个子代理做并行验收/审计后释放。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，call_capability/probe/finish_task 对活栈和边界很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, codegraph, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

工作区存在其他线程/工具台并行写入，finish_task 的硬边界会把非本任务改动混在一起；需要更方便地声明或锁定开工基线。

## 缺少的工具 / 能力

希望有只读的 per-task diff attribution/ownership 工具，区分本 agent 写入、子代理写入、外部线程写入。

## 升级建议

finish_task 的 lint_paths 可以自动识别目录并调用 ruff，而不是把 modules/agent 当文件不存在；边界报告可同时输出 tracked-only 与 tracked+untracked 两个视图。

## 建议移除或合并的工具

无

## 其他备注

本轮子代理策略有效：前端、边界、live capability、后端审计、文档/测试审计分别发现了可执行问题，两个最终审计代理完成后已 close。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1419,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 672,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 652,
    "error": 8,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "code_explore",
    "calls": 643,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 583,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 532,
    "error": 18,
    "avg_duration_seconds": 0.656
  },
  {
    "tool": "worktree_guard",
    "calls": 517,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 482,
    "error": 3,
    "avg_duration_seconds": 4.435
  },
  {
    "tool": "code_impact",
    "calls": 476,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 424,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
