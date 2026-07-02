---
name: "工具台反馈-20260702-162306-capability-contract-worker-r2-活系统验证重点模块 manifest public_actions、re"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "capability-contract-worker-r2"
created: "2026-07-02T16:23:06.666257+00:00"
---

# MCP 使用反馈

## 任务

活系统验证重点模块 manifest public_actions、register_capability、/api/modules/call 一致性，并修复 desktop-tools:list_apps 500。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，routes/capabilities/call_capability 很适合这种契约审计，能快速从声明层走到活系统验证。

## 本次用到的工具

brief, plan_task, worktree_guard, routes, capabilities, code_explore, code_node, code_impact, probe, call_capability, run_test, lint, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

CodeGraph 返回了 knowledge router 的旧片段，和实读磁盘不一致；tail_log 对 backend 返回空，最后需要直接 tail backend/logs/backend.log。worktree 并行变更多，finish_task 能看见但无法区分归属。

## 缺少的工具 / 能力

缺一个 manifest public_actions 与 live /api/modules/capabilities 精确比对工具，可直接按模块输出 missing_live/missing_manifest/min_role drift；缺一个能标记本 agent touched files 的边界摘要。

## 升级建议

给 capabilities 工具增加 live_registry=true 选项，直接对比 manifest 与运行时 registry；tail_log 后端空输出时自动 fallback backend/logs/backend.log；CodeGraph 结果增加 stale 明示或自动重新索引提示。

## 建议移除或合并的工具

无

## 其他备注

本次发现初始 knowledge:classify_pipeline_debt live 缺失是进程未刷新，重启后恢复；实际代码修复是 desktop-tools:list_apps 从旧 app.backend_config 改到 App.public_actions。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 330,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 246,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 170,
    "error": 7,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 168,
    "error": 0,
    "avg_duration_seconds": 0.309
  },
  {
    "tool": "code_impact",
    "calls": 108,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "worktree_guard",
    "calls": 104,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "db_schema",
    "calls": 97,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 94,
    "error": 0,
    "avg_duration_seconds": 2.601
  },
  {
    "tool": "probe",
    "calls": 80,
    "error": 0,
    "avg_duration_seconds": 0.587
  },
  {
    "tool": "plan_task",
    "calls": 72,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
