---
name: "工具台反馈-20260703-082625-codex-conductor-sweep-20260703-r2-Main-session verification and commit"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T08:26:25.309583+00:00"
---

# MCP 使用反馈

## 任务

Main-session verification and commit prep for media-asr r2 boundary hardening

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，probe/call_capability/run_test 能快速完成主会话验收。

## 本次用到的工具

brief, plan_task, worktree_guard, code_impact, code_node, routes, capabilities, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 的 module boundary 会把其他未提交模块和历史 uploads 一起算作越界；在并行子代理脏工作区下需要人工按 stage 范围判断。

## 缺少的工具 / 能力

希望增加按 staged/explicit file list 做模块边界验收的工具，避免并行半成品干扰已验收提交。

## 升级建议

finish_task 可支持 allowed_changed_files 或 compare staged-only，并明确区分全工作区脏与本次提交边界。

## 建议移除或合并的工具

无

## 其他备注

本轮按文件级精确 staging 提交 media-asr，未触碰其他半成品。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 866,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 557,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "call_capability",
    "calls": 371,
    "error": 17,
    "avg_duration_seconds": 0.808
  },
  {
    "tool": "code_explore",
    "calls": 355,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 327,
    "error": 3,
    "avg_duration_seconds": 0.47
  },
  {
    "tool": "code_impact",
    "calls": 312,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "run_test",
    "calls": 312,
    "error": 2,
    "avg_duration_seconds": 3.397
  },
  {
    "tool": "sql",
    "calls": 310,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 304,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 242,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
