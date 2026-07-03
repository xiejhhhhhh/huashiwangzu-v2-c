---
name: "工具台反馈-20260703-064720-codex-agent-module-sweep-20260703-r2-modules/agent 扫雷并修复子 Agent 写保护绕过、无结论"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-module-sweep-20260703-r2"
created: "2026-07-03T06:47:20.819099+00:00"
---

# MCP 使用反馈

## 任务

modules/agent 扫雷并修复子 Agent 写保护绕过、无结论工具错误假成功、skill usage 遥测不可观测。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/code_explore/db_reverse_audit/finish_task 对扫描很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

agent_board 没有独立 heartbeat 工具，重复 claim 会被拒绝，无法严格按“每阶段 heartbeat”落 node_log；finish_task 在多人并行 dirty 工作区会把非本人改动也判边界失败，需要人工解释。

## 缺少的工具 / 能力

缺少 agent_board_heartbeat/progress 工具；缺少按本次 touched files 或允许项目记忆一起做边界验收的模式。

## 升级建议

worktree_guard/finish_task 可支持 baseline snapshot 或 caller-owned changed files，适配并行 agent；db_reverse_audit 输出较长时希望保留完整 requires_flow_probe 列表摘要。

## 建议移除或合并的工具

无

## 其他备注

本次严格未修改 backend/app、frontend/src 或其他模块；完整 test_tool_guidance 的 browser-tools 失败按边界只记录风险。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 653,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 457,
    "error": 0,
    "avg_duration_seconds": 0.02
  },
  {
    "tool": "code_explore",
    "calls": 307,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 290,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 241,
    "error": 2,
    "avg_duration_seconds": 3.593
  },
  {
    "tool": "worktree_guard",
    "calls": 238,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 230,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 199,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "call_capability",
    "calls": 182,
    "error": 12,
    "avg_duration_seconds": 0.708
  },
  {
    "tool": "probe",
    "calls": 176,
    "error": 2,
    "avg_duration_seconds": 0.459
  }
]
```
