---
name: "工具台反馈-20260703-070510-codex-image-gen-sweep-20260703-r2-modules/image-gen r2 扫雷：修复生成参数、记录/文件"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-image-gen-sweep-20260703-r2"
created: "2026-07-03T07:05:10.691148+00:00"
---

# MCP 使用反馈

## 任务

modules/image-gen r2 扫雷：修复生成参数、记录/文件产物、错误语义与 sandbox/manifest 契约。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/routes/capabilities/db_schema/lint/run_test/probe 串起来能快速定位契约漂移。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task/worktree_guard 在并行 worker 共享工作区下会把其他模块和 data/uploads 的改动计为本任务边界失败，需要人工解读；另外活系统未重启时无法用 call_capability 验证本轮未加载的新代码。

## 缺少的工具 / 能力

缺少按 agent 或按本次 touched-files 过滤的边界检查；缺少“临时生成文件+record 自动清理”的模块探针工具。

## 升级建议

worktree_guard/finish_task 可支持 allowed_prefixes 附加 开发文档/项目记忆，并增加 only_touched_by_current_agent 或 git pathspec 模式；probe/call_capability 可提示当前后端代码是否已加载最新 mtime。

## 建议移除或合并的工具

无

## 其他备注

本次未重启共享后端，使用直接加载修改后模块代码的 placeholder 生成探针验证 landscape 产物 1280x720，并清理了测试产物。

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
