---
name: "工具台反馈-20260703-072650-codex-douyin-delivery-sweep-20260703-r2-modules/douyin-delivery r2 sweep: ad"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-douyin-delivery-sweep-20260703-r2"
created: "2026-07-03T07:26:50.972410+00:00"
---

# MCP 使用反馈

## 任务

modules/douyin-delivery r2 sweep: added account/material/delivery-task/cleanup contracts, hardened status and failure semantics, validated live DB cleanup.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，routes/capabilities/db_reverse_audit 对空表反推和契约确认很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的边界检查只支持 module_key 默认 allowed_prefix，无法把本任务允许的 开发文档/项目记忆 纳入，且全仓并行 dirty 会让结果 success=false，需要人工解读 forbidden_hit_count。

## 缺少的工具 / 能力

希望有按 marker 一键创建/清理探针数据的模块级 probe recipe，或者 probe 支持把上一步响应字段自动带入下一步。

## 升级建议

finish_task 可增加 allowed_prefixes 参数，并在报告中单独区分“本 agent 改动范围”和“全仓已有脏文件”。

## 建议移除或合并的工具

无

## 其他备注

call_capability 权限缓存需要后端重启后才反映新的 min_role，这符合进程内注册表机制，但工具提示可以更明确。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 721,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 501,
    "error": 0,
    "avg_duration_seconds": 0.023
  },
  {
    "tool": "code_explore",
    "calls": 325,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 286,
    "error": 16,
    "avg_duration_seconds": 0.694
  },
  {
    "tool": "run_test",
    "calls": 281,
    "error": 2,
    "avg_duration_seconds": 3.649
  },
  {
    "tool": "worktree_guard",
    "calls": 271,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 254,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 225,
    "error": 2,
    "avg_duration_seconds": 0.515
  },
  {
    "tool": "db_schema",
    "calls": 220,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
