---
name: "工具台反馈-20260704-114252-codex-content-artifact-publish-r1-ContentPackage 到 Artifact 发布闭环补修与最终验"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:42:52.257421+00:00"
---

# MCP 使用反馈

## 任务

ContentPackage 到 Artifact 发布闭环补修与最终验收：修复无源 write_ir package publish 失败，补测试，完成 capability/REST 活栈验证并清理数据。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph、probe/call_capability、finish_task 对定位和验收很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, sql, probe, call_capability, run_test, lint, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 在并发脏工作区下需要手工维护 baseline；lint 工具对目录路径 backend/app/services/content 报文件不存在，实际命令行 ruff 可直接检查目录。

## 缺少的工具 / 能力

希望有专门的测试数据 cleanup helper，可按 artifact_id/package_id/file_id 一次清理 DB row 和磁盘文件，并自动回报计数差分。

## 升级建议

lint 工具支持目录路径；finish_task 可接收并发 baseline 文件保存/复用，减少长 baseline 参数。

## 建议移除或合并的工具

无

## 其他备注

本轮发现执行信验收中的 content:write_ir -> content:publish 真链路比服务层单测更能暴露无源 package 的 publish 缺口。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 259,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 151,
    "error": 0,
    "avg_duration_seconds": 0.334
  },
  {
    "tool": "probe",
    "calls": 105,
    "error": 3,
    "avg_duration_seconds": 0.349
  },
  {
    "tool": "worktree_guard",
    "calls": 101,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "call_capability",
    "calls": 96,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "sql",
    "calls": 91,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 79,
    "error": 0,
    "avg_duration_seconds": 0.746
  },
  {
    "tool": "plan_task",
    "calls": 77,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 75,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "run_test",
    "calls": 58,
    "error": 0,
    "avg_duration_seconds": 5.004
  }
]
```
