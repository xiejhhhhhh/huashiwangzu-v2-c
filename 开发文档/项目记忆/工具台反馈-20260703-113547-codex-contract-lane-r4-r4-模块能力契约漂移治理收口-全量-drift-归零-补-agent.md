---
name: "工具台反馈-20260703-113547-codex-contract-lane-r4-R4 模块能力契约漂移治理收口：全量 drift 归零，补 agent/"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-contract-lane-r4"
created: "2026-07-03T11:35:47.793487+00:00"
---

# MCP 使用反馈

## 任务

R4 模块能力契约漂移治理收口：全量 drift 归零；主会话退回 agent/bootstrap 别名化产品改动，最终以 contract scanner 修正和既有契约修复为准。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，contract diff 工具对 manifest/runtime 参数漂移很有效。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, capability_contract_diff, lint, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

并行 worker/主会话期间 HEAD 多次前进，部分修复已被提交，导致需要反复核对 git status 与实际文件内容；agent/bootstrap 别名化会让产品代码为工具限制让路，主会话最终选择退回。

## 缺少的工具 / 能力

无

## 升级建议

建议 capability_contract_diff 对函数内 static capabilities tuple 的注册循环做顺序无关识别，避免 ast.walk 先遇到调用、后遇到赋值时误报 uncheckable。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1121,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 620,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 488,
    "error": 25,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 483,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 464,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "call_capability",
    "calls": 454,
    "error": 17,
    "avg_duration_seconds": 0.712
  },
  {
    "tool": "run_test",
    "calls": 403,
    "error": 2,
    "avg_duration_seconds": 3.294
  },
  {
    "tool": "code_impact",
    "calls": 394,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 382,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 333,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
