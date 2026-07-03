---
name: "工具台反馈-20260703-101208-backend-upload-temp-cleanup-r3-修复普通上传失败路径临时文件泄漏并治理 backend/data 运行态"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "backend-upload-temp-cleanup-r3"
created: "2026-07-03T10:12:08.525759+00:00"
---

# MCP 使用反馈

## 任务

修复普通上传失败路径临时文件泄漏并治理 backend/data 运行态产物忽略/误跟踪。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅：brief/plan_task/worktree_guard/code_explore/lint/run_test/probe/finish_task 串起来能覆盖开工到验收。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, memory_write, lint, run_test, probe, tail_log, finish_task, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 对 git rm --cached 的运行态产物会显示为删除，若 allowed_prefixes 未覆盖具体运行态路径容易误判；并发代理产生的记忆和代码改动也会混入边界结果，需要人工解释。

## 缺少的工具 / 能力

希望 worktree_guard 支持 expected_cached_removals 或 ignore_concurrent_dirty 参数，用于并行多代理场景区分本代理改动与外部改动。

## 升级建议

finish_task 可支持 allowed_prefixes/expected_untracked_memory 参数，并在报告里单独列出 staged runtime untrack。

## 建议移除或合并的工具

无

## 其他备注

CodeGraph CLI 与 MCP code_explore 都可用；本次未 commit/push。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1021,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 583,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 410,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 393,
    "error": 17,
    "avg_duration_seconds": 0.78
  },
  {
    "tool": "probe",
    "calls": 368,
    "error": 3,
    "avg_duration_seconds": 0.457
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 359,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 347,
    "error": 2,
    "avg_duration_seconds": 3.231
  },
  {
    "tool": "worktree_guard",
    "calls": 336,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 283,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
