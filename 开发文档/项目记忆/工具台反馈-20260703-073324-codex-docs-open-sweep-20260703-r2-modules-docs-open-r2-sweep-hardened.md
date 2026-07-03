---
name: "工具台反馈-20260703-073324-codex-docs-open-sweep-20260703-r2-modules/docs-open r2 sweep: hardened"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-docs-open-sweep-20260703-r2"
created: "2026-07-03T07:33:24.764805+00:00"
---

# MCP 使用反馈

## 任务

modules/docs-open r2 sweep: hardened scoped token auth boundaries, input validation, false-success content semantics, manifest/sandbox docs.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph + 工具台能快速定位 docs-open 的鉴权链路和能力声明。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, probe, call_capability, tail_log, run_test, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在多人并发时会把其他 worker 改动一起算作边界失败，需要人工解释 baseline；call_capability 命中新代码前依赖后端重启，反馈里不易区分旧进程和新代码问题。

## 缺少的工具 / 能力

希望有一个按 agent/task_id 标记本轮改动范围的 guard，或能传 baseline timestamp/status 只校验本 agent 后续新增改动。

## 升级建议

probe/call_capability 若能返回后端进程启动时间、模块文件 mtime 或是否热加载，会更容易判断活系统是否已加载本轮代码。

## 建议移除或合并的工具

无

## 其他备注

routes 一开始连接失败，后续恢复；tail_log 空输出可接受但最好返回日志文件路径和读取状态，方便判断是真的无日志还是没找到日志。

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
    "calls": 511,
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
