---
name: "工具台反馈-20260703-073304-codex-im-sweep-20260703-r2-modules/im r2 sweep：修复消息契约、未读/已读逻辑、c"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-im-sweep-20260703-r2"
created: "2026-07-03T07:33:04.482431+00:00"
---

# MCP 使用反馈

## 任务

modules/im r2 sweep：修复消息契约、未读/已读逻辑、capability 失败语义、前端建会话路径和 sandbox 真测。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台能快速给出 IM 路由/能力/表结构和已有脏工作区边界。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 在并发 worker 很多时会整体 false，需要人工区分本 agent 改动与其他 worker 已有脏区；frontend build 会触发 scan-modules 写 generated 文件，模块任务容易误触禁止区。

## 缺少的工具 / 能力

希望增加按 agent/起始快照过滤的 boundary delta 工具，或支持传入 baseline 后只报告本 agent 新增越界 diff。

## 升级建议

finish_task 可以自动纳入活栈是否加载最新文件的检测，例如新增 route 405/404 时提示需重启后端。

## 建议移除或合并的工具

无

## 其他备注

call_capability 对旧 IM 内嵌 success:false 已返回 422，说明框架层已有防假绿保护；但常驻后端未重载新 router，新增 POST /api/im/conversations 需重启后验。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 740,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 510,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 327,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 295,
    "error": 16,
    "avg_duration_seconds": 0.684
  },
  {
    "tool": "run_test",
    "calls": 287,
    "error": 2,
    "avg_duration_seconds": 3.639
  },
  {
    "tool": "worktree_guard",
    "calls": 277,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 259,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 243,
    "error": 2,
    "avg_duration_seconds": 0.517
  },
  {
    "tool": "db_schema",
    "calls": 225,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
