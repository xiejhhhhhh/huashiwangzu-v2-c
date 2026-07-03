---
name: "工具台反馈-20260703-070511-codex-office-gen-sweep-20260703-r2-modules/office-gen r2 sweep: harden "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-office-gen-sweep-20260703-r2"
created: "2026-07-03T07:05:11.791027+00:00"
---

# MCP 使用反馈

## 任务

modules/office-gen r2 sweep: harden empty output guards, Content IR compatibility, conversion non-empty check, manifest/docs/tests

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/code_node/run_test 对模块扫雷很省时间。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, call_capability, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

lint 工具对目录路径判定为不存在，只能改用 backend/.venv/bin/python -m ruff check；finish_task 的 module_key 边界检查不能把必要的 开发文档/项目记忆 作为允许路径一起纳入，且并行 worker dirty 会导致 success=false 噪音。

## 缺少的工具 / 能力

agent_board claim/heartbeat 未暴露；希望有按 agent/worktree 过滤的 dirty 边界视图，能排除其他 worker 的既有改动。

## 升级建议

lint 支持目录路径或在报错中明确只支持文件；finish_task 增加 allowed_prefixes 参数，并区分本 agent 新增改动与全工作区并行改动。

## 建议移除或合并的工具

无

## 其他备注

未强制重启主后端，因为当前多 worker 共用活栈；活系统做了 health 和空输入失败验证，代码级新 router ValidationError 行为由单测/ruff覆盖。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 691,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 486,
    "error": 0,
    "avg_duration_seconds": 0.022
  },
  {
    "tool": "code_explore",
    "calls": 315,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 300,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 273,
    "error": 2,
    "avg_duration_seconds": 3.74
  },
  {
    "tool": "worktree_guard",
    "calls": 252,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 243,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "call_capability",
    "calls": 237,
    "error": 12,
    "avg_duration_seconds": 0.641
  },
  {
    "tool": "db_schema",
    "calls": 206,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 194,
    "error": 2,
    "avg_duration_seconds": 0.447
  }
]
```
