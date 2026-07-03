---
name: "工具台反馈-20260703-111306-codex-codemap-feedback-loop-r3-总收口：codemap 反馈闭环、锁能力、manifest、sandbo"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:13:06.652914+00:00"
---

# MCP 使用反馈

## 任务

总收口：codemap 反馈闭环、锁能力、manifest、sandbox、README 大域扫雷完成

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台足够支撑从代码定位到活栈验证的闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, probe, call_capability, sql, run_test, lint, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

共享工作区多 agent dirty 文件导致 finish_task 边界结果为 false；tail_log 返回空；lint 不能直接吃目录。

## 缺少的工具 / 能力

需要一个能按本 agent 触碰文件或指定 allowed_prefixes+项目记忆运行的 finish_task；需要安全 cleanup helper。

## 升级建议

finish_task 支持 allowed_prefixes、baseline dirty、project memory 例外；lint 支持目录展开；tail_log 修复 backend 参数。

## 建议移除或合并的工具

无

## 其他备注

未提交未推送；后端已重启到 33000 并保持运行。

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
    "calls": 451,
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
