---
name: "工具台反馈-20260703-180657-codex-post-convergence-repair-修复后收敛补漏：MCP 长任务后台 job、进程树清理、reset 级联"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-post-convergence-repair"
created: "2026-07-03T18:06:57.727346+00:00"
---

# MCP 使用反馈

## 任务

修复后收敛补漏：MCP 长任务后台 job、进程树清理、reset 级联安全、UI 5.2 假绿。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，项目工具台的边界守卫和 probe 对收工验证很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, codegraph CLI, probe, finish_task, memory_write, mcp_feedback, subagents

## 卡点 / 不顺手的地方

当前运行中的 MCP server 无法热加载新增 tool_job_* schema，需要通过 stdio 直启 server.py 验证新工具；长 release_gate 相关测试耗时较长。

## 缺少的工具 / 能力

若工具台能提供“用当前工作区临时启动 MCP 并 call_tool”的内置验证工具，会比手写 mcp client snippet 更方便。

## 升级建议

建议现有 release_gate/run_test/smoke_all/module_sandbox_matrix/lint 在 MCP 层提示优先使用 tool_job_submit，或由工具台自动将超过阈值的调用转后台 job。

## 建议移除或合并的工具

无。

## 其他备注

子代理并行处理 reset 和 UI 两个互不重叠区域，主代理处理 dev_toolkit/job 主干，集成顺利。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1247,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "lint",
    "calls": 650,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "sql",
    "calls": 566,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 556,
    "error": 8,
    "avg_duration_seconds": 0.455
  },
  {
    "tool": "code_explore",
    "calls": 526,
    "error": 0,
    "avg_duration_seconds": 0.326
  },
  {
    "tool": "call_capability",
    "calls": 495,
    "error": 17,
    "avg_duration_seconds": 0.684
  },
  {
    "tool": "run_test",
    "calls": 450,
    "error": 3,
    "avg_duration_seconds": 4.591
  },
  {
    "tool": "worktree_guard",
    "calls": 441,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 440,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 368,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
