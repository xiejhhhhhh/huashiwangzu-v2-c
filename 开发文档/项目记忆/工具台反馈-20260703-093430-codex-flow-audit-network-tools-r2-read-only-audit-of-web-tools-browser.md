---
name: "工具台反馈-20260703-093430-codex-flow-audit-network-tools-r2-Read-only audit of web-tools/browser"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-flow-audit-network-tools-r2"
created: "2026-07-03T09:34:30.589241+00:00"
---

# MCP 使用反馈

## 任务

Read-only audit of web-tools/browser-tools/github-search/agent outbound request chains and network tool failure semantics.

## 顺畅度

- 评分：4/5
- 体感：Mostly smooth: CodeGraph plus routes/capabilities gave enough source and contract evidence without broad scanning.

## 本次用到的工具

brief, plan_task, worktree_guard, routes, capabilities, code_explore, code_node, code_impact, tail_log, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

code_explore sometimes returned very broad/truncated Agent output, so I had to follow up with code_node and small sed ranges after CodeGraph定位.

## 缺少的工具 / 能力

A focused outbound-network audit tool that lists http clients, trust_env, timeout bounds, streaming/body limits, and SSRF validator usage would speed this up.

## 升级建议

Add a project_toolkit network_audit helper and a codegraph query preset for module capability handlers plus Agent skill_use path.

## 建议移除或合并的工具

无

## 其他备注

Initial worktree_guard showed dirty web-tools files, but final finish_task/worktree_guard reported clean; likely concurrent task cleanup. No code edits or commit by this agent.

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 940,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 567,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "call_capability",
    "calls": 387,
    "error": 17,
    "avg_duration_seconds": 0.788
  },
  {
    "tool": "code_explore",
    "calls": 381,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 344,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 335,
    "error": 3,
    "avg_duration_seconds": 0.466
  },
  {
    "tool": "code_impact",
    "calls": 331,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 322,
    "error": 2,
    "avg_duration_seconds": 3.316
  },
  {
    "tool": "worktree_guard",
    "calls": 314,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 258,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
