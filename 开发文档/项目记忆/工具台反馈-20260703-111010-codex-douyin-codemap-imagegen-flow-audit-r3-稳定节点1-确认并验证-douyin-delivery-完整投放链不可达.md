---
name: "工具台反馈-20260703-111010-codex-douyin-codemap-imagegen-flow-audit-r3-稳定节点1：确认并验证 douyin-delivery 完整投放链不可达"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-douyin-codemap-imagegen-flow-audit-r3"
created: "2026-07-03T11:10:10.780889+00:00"
---

# MCP 使用反馈

## 任务

稳定节点1：确认并验证 douyin-delivery 完整投放链不可达问题的产品定位收敛与手动交接闭环修复

## 顺畅度

- 评分：4/5
- 体感：工具台组件可直接调用完成落盘，但恢复后 MCP namespace 未暴露，需用 dev_toolkit.memory_tools.handle_tool 兜底。

## 本次用到的工具

worktree_guard(尝试), git diff, ruff, pytest, live HTTP probe, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

恢复后 mcp__project_toolkit 命名空间不可用，tool_search 也未发现项目工具台工具；只能直接调用工具台组件。

## 缺少的工具 / 能力

希望恢复后仍能暴露项目工具台 MCP，或提供稳定的本地 CLI wrapper 调 memory_write/mcp_feedback。

## 升级建议

memory_write/mcp_feedback 可提供官方 CLI shim，避免 MCP namespace 丢失时 agent 手写或自行拼 JSON-RPC。

## 建议移除或合并的工具

无

## 其他备注

本节点只处理 douyin-delivery 域；其他 codemap/agent/gateway 改动未触碰。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1103,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 614,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "code_explore",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 444,
    "error": 5,
    "avg_duration_seconds": 0.446
  },
  {
    "tool": "sql",
    "calls": 441,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 430,
    "error": 17,
    "avg_duration_seconds": 0.737
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 386,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 369,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 316,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
