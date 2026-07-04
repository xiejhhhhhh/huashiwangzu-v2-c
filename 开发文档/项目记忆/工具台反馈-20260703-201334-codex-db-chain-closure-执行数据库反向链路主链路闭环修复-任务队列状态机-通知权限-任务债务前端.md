---
name: "工具台反馈-20260703-201334-codex-db-chain-closure-执行数据库反向链路主链路闭环修复：任务队列状态机、通知权限、任务债务前端"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-db-chain-closure"
created: "2026-07-03T20:13:34.021296+00:00"
---

# MCP 使用反馈

## 任务

执行数据库反向链路主链路闭环修复：任务队列状态机、通知权限、任务债务前端入口、dev_toolkit 配置迁移、release gate JSON 增强与健康阻断修复。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，probe/lint/run_test/finish_task 能把活系统、静态检查和边界检查连起来。

## 本次用到的工具

brief, plan_task, worktree_guard, db_reverse_audit, routes, db_schema, code_explore/codegraph, probe, lint, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 baseline_paths 对目录前缀识别不够直观，传入 modules/agent/ 仍把并行脏区标成 new_since_baseline；最终只能用 allowed_prefixes 和 risk_note 说明。

## 缺少的工具 / 能力

希望 release_gate MCP 包装工具能直接暴露 skip_ui/preflight/sandbox_jobs/frontend_jobs，并返回压缩后的 RELEASE_GATE_JSON 关键字段。

## 升级建议

finish_task 可以支持 baseline_prefixes，并在报告中把 baseline prefix 下的 dirty 明确归类为 acknowledged baseline。

## 建议移除或合并的工具

无

## 其他备注

本轮使用直接命令补跑 frontend build 和 module_sandbox_matrix；MCP probe 对权限和任务审计验证很好用。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1421,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 673,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 668,
    "error": 8,
    "avg_duration_seconds": 0.445
  },
  {
    "tool": "code_explore",
    "calls": 647,
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
    "calls": 535,
    "error": 18,
    "avg_duration_seconds": 0.655
  },
  {
    "tool": "worktree_guard",
    "calls": 519,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 485,
    "error": 3,
    "avg_duration_seconds": 4.432
  },
  {
    "tool": "code_impact",
    "calls": 477,
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
