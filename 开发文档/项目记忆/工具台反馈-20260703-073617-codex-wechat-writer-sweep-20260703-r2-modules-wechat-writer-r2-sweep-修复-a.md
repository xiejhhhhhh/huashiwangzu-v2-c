---
name: "工具台反馈-20260703-073617-codex-wechat-writer-sweep-20260703-r2-modules/wechat-writer r2 sweep: 修复 a"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-wechat-writer-sweep-20260703-r2"
created: "2026-07-03T07:36:17.597933+00:00"
---

# MCP 使用反馈

## 任务

modules/wechat-writer r2 sweep: 修复 async startup init warning、参数边界与假成功语义，补 sandbox 验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph 与工具台能快速定位 init_db/router/services 和契约。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在并发 worker 场景会整体报红，需要人工区分本任务改动与其他 worker 既有改动；call_capability 遇到 server disconnected 时缺少后端日志关联。

## 缺少的工具 / 能力

希望增加按 agent/allowed prefix 过滤的边界守卫视图，以及 call_capability 自动附带最近 backend log/request id。

## 升级建议

finish_task 可接收 known_concurrent_prefixes，减少并行扫雷时的噪声。

## 建议移除或合并的工具

无

## 其他备注

run_test 很好用；本次活系统新代码需要主会话重启后端才能完全验证 startup warning 消失。

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
    "calls": 513,
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
    "calls": 300,
    "error": 17,
    "avg_duration_seconds": 0.747
  },
  {
    "tool": "run_test",
    "calls": 288,
    "error": 2,
    "avg_duration_seconds": 3.628
  },
  {
    "tool": "worktree_guard",
    "calls": 278,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 262,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 247,
    "error": 2,
    "avg_duration_seconds": 0.514
  },
  {
    "tool": "db_schema",
    "calls": 225,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
