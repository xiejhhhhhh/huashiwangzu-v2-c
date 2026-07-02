---
name: "工具台反馈-20260702-162522-knowledge-schema-evolution-worker-深挖 knowledge 链路并实施结构性 schema 演进：新增 p"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "knowledge-schema-evolution-worker"
created: "2026-07-02T16:25:22.758985+00:00"
---

# MCP 使用反馈

## 任务

深挖 knowledge 链路并实施结构性 schema 演进：新增 pipeline run/stage diagnostics 表，补 raw/fusion 产物诊断字段，接入 orchestrator，并根据评审修复诊断写入隔离/rollback 语义。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台对活栈 probe、schema 检查和 focused tests 很有效。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, sql, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

run_test 对 modules/knowledge/backend/tests 整目录时 PYTHONPATH/环境加载不足，导致 app 模块和 JWT_SECRET/测试库问题；worktree_guard 在多 worker 并行时会把其他 worker dirty 一并报越界，需要报告中人工区分。

## 缺少的工具 / 能力

希望 run_test 支持显式 env_file=backend/.env 和 PYTHONPATH 追加 backend；希望 worktree_guard 可传 baseline commit 或 owned_paths 来区分本 agent 改动与并行 worker 改动。

## 升级建议

为模块任务增加 `git diff --name-only -- <module_path>` 风格的边界子视图；run_test 可检测 pytest 导入 app 失败时提示使用 backend pytest.ini/env。

## 建议移除或合并的工具

无

## 其他备注

CodeGraph 对后端服务文件定位很快；db_reverse_audit 对 kb_* 当前数据状态判断有帮助。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 334,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 251,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 171,
    "error": 0,
    "avg_duration_seconds": 0.309
  },
  {
    "tool": "sql",
    "calls": 170,
    "error": 7,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 110,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 106,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 101,
    "error": 0,
    "avg_duration_seconds": 2.479
  },
  {
    "tool": "db_schema",
    "calls": 97,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 83,
    "error": 0,
    "avg_duration_seconds": 0.575
  },
  {
    "tool": "plan_task",
    "calls": 74,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
