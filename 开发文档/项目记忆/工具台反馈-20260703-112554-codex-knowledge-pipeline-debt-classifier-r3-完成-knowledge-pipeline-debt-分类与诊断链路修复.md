---
name: "工具台反馈-20260703-112554-codex-knowledge-pipeline-debt-classifier-r3-完成 knowledge pipeline debt 分类与诊断链路修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-knowledge-pipeline-debt-classifier-r3"
created: "2026-07-03T11:25:54.423797+00:00"
---

# MCP 使用反馈

## 任务

完成 knowledge pipeline debt 分类与诊断链路修复

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，SQL 反推真实债务再用 CodeGraph 定点改代码的路径很高效。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, db_reverse_audit, sql, lint, run_test, probe, call_capability, tail_log, _restart_backend, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 module_key 边界默认不包含项目记忆，和本任务“必要项目记忆允许”的边界有一点冲突，需要另跑 worktree_guard 补充确认。

## 缺少的工具 / 能力

缺一个大治理接口的 summary-only capability/probe 输出裁剪参数。

## 升级建议

finish_task 建议支持 allowed_prefixes，或 module_key 自动允许 开发文档/项目记忆/ 这种规则里明确允许的归因文件。

## 建议移除或合并的工具

无

## 其他备注

未提交、未推送、未清理生产数据。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1118,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 617,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 478,
    "error": 6,
    "avg_duration_seconds": 0.447
  },
  {
    "tool": "sql",
    "calls": 474,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 460,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 451,
    "error": 17,
    "avg_duration_seconds": 0.715
  },
  {
    "tool": "run_test",
    "calls": 402,
    "error": 2,
    "avg_duration_seconds": 3.299
  },
  {
    "tool": "code_impact",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 375,
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
