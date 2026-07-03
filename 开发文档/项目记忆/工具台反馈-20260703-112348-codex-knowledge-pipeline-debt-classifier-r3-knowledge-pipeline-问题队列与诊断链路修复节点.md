---
name: "工具台反馈-20260703-112348-codex-knowledge-pipeline-debt-classifier-r3-knowledge pipeline 问题队列与诊断链路修复节点"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-knowledge-pipeline-debt-classifier-r3"
created: "2026-07-03T11:23:48.489411+00:00"
---

# MCP 使用反馈

## 任务

knowledge pipeline 问题队列与诊断链路修复节点

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，SQL 与 CodeGraph 组合能快速把任务队列、诊断表和状态机断路对齐。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, db_reverse_audit, sql, lint, run_test, _restart_backend

## 卡点 / 不顺手的地方

call_capability 大结果容易过长，按 marker 用 probe dry-run 更适合验证细分类。

## 缺少的工具 / 能力

希望 classify_pipeline_debt 这类能力支持只返回 summary/problem_queue 的参数，减少大 items 输出。

## 升级建议

probe/call_capability 可增加 response_selector 或 max_items 参数，便于活栈验证大治理接口。

## 建议移除或合并的工具

无

## 其他备注

本节点未做数据清理或提交。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1117,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 616,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 473,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 469,
    "error": 6,
    "avg_duration_seconds": 0.45
  },
  {
    "tool": "code_explore",
    "calls": 460,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 447,
    "error": 17,
    "avg_duration_seconds": 0.719
  },
  {
    "tool": "run_test",
    "calls": 401,
    "error": 2,
    "avg_duration_seconds": 3.265
  },
  {
    "tool": "code_impact",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 373,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 327,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
