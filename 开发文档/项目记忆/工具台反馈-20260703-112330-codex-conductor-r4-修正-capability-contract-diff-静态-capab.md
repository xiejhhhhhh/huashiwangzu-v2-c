---
name: "工具台反馈-20260703-112330-codex-conductor-r4-修正 capability_contract_diff 静态 capab"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-r4"
created: "2026-07-03T11:23:30.036594+00:00"
---

# MCP 使用反馈

## 任务

修正 capability_contract_diff 静态 capabilities 表解析，并收口 agent/desktop-tools/image-gen 契约漂移。

## 顺畅度

- 评分：4/5
- 体感：contract diff 工具很有价值，直接把 manifest/runtime drift 变成可验收门槛。

## 本次用到的工具

capability_contract_diff, ruff, pytest, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

pytest 同时跑多个 sandbox/test_module.py 会 import mismatch，需要 --import-mode=importlib；run_test 可考虑默认支持该模式或按文件分进程。

## 缺少的工具 / 能力

缺少按模块 contract drift 自动生成修复建议的工具。

## 升级建议

capability_contract_diff 后续可直接输出建议 patch 草案；run_test 可内建 sandbox 同名文件防冲突策略。

## 建议移除或合并的工具

无

## 其他备注

本次发现 scanner 位序 bug，已补回归测试。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1117,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 616,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 473,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 469,
    "error": 6,
    "avg_duration_seconds": 0.45
  },
  {
    "tool": "code_explore",
    "calls": 460,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 447,
    "error": 17,
    "avg_duration_seconds": 0.719
  },
  {
    "tool": "run_test",
    "calls": 401,
    "error": 2,
    "avg_duration_seconds": 3.265
  },
  {
    "tool": "code_impact",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 373,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 327,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
