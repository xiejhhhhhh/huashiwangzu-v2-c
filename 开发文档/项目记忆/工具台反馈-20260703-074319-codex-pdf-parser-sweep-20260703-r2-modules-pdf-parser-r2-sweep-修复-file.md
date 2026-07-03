---
name: "工具台反馈-20260703-074319-codex-pdf-parser-sweep-20260703-r2-modules/pdf-parser r2 sweep: 修复 file"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-pdf-parser-sweep-20260703-r2"
created: "2026-07-03T07:43:19.455478+00:00"
---

# MCP 使用反馈

## 任务

modules/pdf-parser r2 sweep: 修复 file_id 入参错误语义、空解析假成功、表格空返回边界，并强化 sandbox 真样例验收

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree_guard/codegraph/lint/run_test/probe/call_capability 串起来能覆盖模块扫雷主流程。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的边界检查只允许 modules/{key}，无法把本任务允许的 开发文档/项目记忆/** 一并视为合规；在并发脏工作区里会标 success=false，需要人工解读。call_capability 返回 500 时 tail_log 为空，定位旧代码/未重载需要额外本地验证。

## 缺少的工具 / 能力

希望 finish_task 支持 allowed_prefixes 参数；希望 call_capability/probe 能返回当前 backend 进程是否已加载文件 mtime 或模块 import 时间，便于判断是否需要重启。

## 升级建议

为 parser 类模块提供标准验收 recipe：manifest/register 对齐、run_uploaded_file_capability 使用、空 blocks/resources 语义、真实样例 sandbox pytest。

## 建议移除或合并的工具

无

## 其他备注

本次未重启常驻 33000，遵守任务要求；活栈正向解析通过，负向新语义通过本地导入验证。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 762,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 523,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 332,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 317,
    "error": 17,
    "avg_duration_seconds": 0.721
  },
  {
    "tool": "sql",
    "calls": 303,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 294,
    "error": 2,
    "avg_duration_seconds": 3.564
  },
  {
    "tool": "worktree_guard",
    "calls": 283,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 270,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 270,
    "error": 2,
    "avg_duration_seconds": 0.491
  },
  {
    "tool": "db_schema",
    "calls": 228,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
