---
name: "工具台反馈-20260703-115333-codex-r5-knowledge-source-unavailable-a-R5 knowledge source-unavailable 状态机 "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-r5-knowledge-source-unavailable-a"
created: "2026-07-03T11:53:33.379589+00:00"
---

# MCP 使用反馈

## 任务

R5 knowledge source-unavailable 状态机 ready 收口

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 focused run_test 能快速定位与验证。

## 本次用到的工具

plan_task,worktree_guard,code_explore,code_node,code_impact,routes,capabilities,db_schema,lint,run_test,call_capability,sql,memory_write,finish_task

## 卡点 / 不顺手的地方

worktree_guard 正确暴露了并行 worker 的外部 dirty，但 finish 阶段会因既有 dirty 标红，需要人工区分本 worker 实际 diff。

## 缺少的工具 / 能力

无

## 升级建议

worktree_guard/finish_task 如果能支持 baseline token 或 since-start snapshot，会更适合并行 worker 精准验收边界。

## 建议移除或合并的工具

无

## 其他备注

本次未使用 apply/reconcile，只做只读 dry-run 和 SQL 证据。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1137,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 628,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 499,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 484,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 471,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "call_capability",
    "calls": 458,
    "error": 17,
    "avg_duration_seconds": 0.709
  },
  {
    "tool": "run_test",
    "calls": 413,
    "error": 2,
    "avg_duration_seconds": 3.274
  },
  {
    "tool": "code_impact",
    "calls": 403,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 340,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
