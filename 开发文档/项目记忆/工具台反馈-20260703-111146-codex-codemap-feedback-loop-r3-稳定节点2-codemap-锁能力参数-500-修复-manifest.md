---
name: "工具台反馈-20260703-111146-codex-codemap-feedback-loop-r3-稳定节点2：codemap 锁能力参数 500 修复，manifest/"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:11:46.874656+00:00"
---

# MCP 使用反馈

## 任务

稳定节点2：codemap 锁能力参数 500 修复，manifest/sandbox/README 对齐

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，活栈 call_capability 很快复现锁能力 500 并验证修复。

## 本次用到的工具

code_explore, code_node, code_impact, capabilities, call_capability, probe, run_test, lint, worktree_guard, memory_write

## 卡点 / 不顺手的地方

worktree_guard 对共享脏工作区只能整体失败，不易表达“本 agent 只改某路径”；tail_log 仍返回空，需要手动 tail。

## 缺少的工具 / 能力

希望有按 since/base 或 touched-by-agent 的边界守卫；希望 call_capability 对内层 success false 的 HTTP 状态映射在输出里解释来源。

## 升级建议

worktree_guard 可支持 allowed_dirty_baseline 或 only_prefix_diff 模式；tail_log 修复 backend 参数。

## 建议移除或合并的工具

无

## 其他备注

本节点保持 modules/codemap/** 范围，未修改框架或其他模块。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1112,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 614,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 450,
    "error": 5,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "code_explore",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 444,
    "error": 17,
    "avg_duration_seconds": 0.722
  },
  {
    "tool": "sql",
    "calls": 442,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 370,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 317,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
