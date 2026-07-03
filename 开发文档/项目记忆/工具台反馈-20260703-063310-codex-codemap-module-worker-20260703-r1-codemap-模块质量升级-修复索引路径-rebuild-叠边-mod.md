---
name: "工具台反馈-20260703-063310-codex-codemap-module-worker-20260703-r1-codemap 模块质量升级：修复索引路径、rebuild 叠边、mod"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-codemap-module-worker-20260703-r1"
created: "2026-07-03T06:33:10.293286+00:00"
---

# MCP 使用反馈

## 任务

codemap 模块质量升级：修复索引路径、rebuild 叠边、module_map 500/HTTP 422、错误假成功、锁持久化和 feedback/stats/rebuild 可信度口径，并补 README 验收矩阵。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree_guard/code_explore/db_reverse_audit/probe/call_capability 能快速闭环到真问题。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_reverse_audit, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write, agent_board_claim, agent_board_heartbeat

## 卡点 / 不顺手的地方

tail_log 有时返回空；worktree_guard 在多人并行 dirty 很多时首次输出噪声大，但 finish_task 的模块边界结果很好用。

## 缺少的工具 / 能力

希望有专门的 runtime artifact cleanup/ignore 检查工具，能提示模块 data 目录是否已被 gitignore 覆盖。

## 升级建议

call_capability 的外层/内层 success 可以提供一个折叠后的 verdict 字段，减少人工判断双层 envelope。

## 建议移除或合并的工具

无

## 其他备注

本次活系统验证发现 rebuild 叠边是关键收获；db_reverse_audit 对 feedback 空表链路很有帮助。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 613,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 451,
    "error": 0,
    "avg_duration_seconds": 0.019
  },
  {
    "tool": "code_explore",
    "calls": 293,
    "error": 0,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "sql",
    "calls": 272,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 232,
    "error": 2,
    "avg_duration_seconds": 3.627
  },
  {
    "tool": "worktree_guard",
    "calls": 231,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 210,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 185,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 166,
    "error": 2,
    "avg_duration_seconds": 0.468
  },
  {
    "tool": "call_capability",
    "calls": 163,
    "error": 12,
    "avg_duration_seconds": 0.756
  }
]
```
