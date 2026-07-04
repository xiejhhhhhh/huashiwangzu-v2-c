---
name: "工具台反馈-20260704-135859-codex-ui-full-gate-vision-fallback-执行 UI Full Gate 与视觉链路模型降级总收口"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-ui-full-gate-vision-fallback"
created: "2026-07-04T13:58:59.646040+00:00"
---

# MCP 使用反馈

## 任务

执行 UI Full Gate 与视觉链路模型降级总收口

## 顺畅度

- 评分：2/5
- 体感：MCP transport 不顺畅，工具函数本身可用但会话 MCP 多次 Transport closed。

## 本次用到的工具

brief, plan_task, worktree_guard, finish_task, memory_write, mcp_feedback, release_gate(shell fallback), pytest, npm build, Playwright

## 卡点 / 不顺手的地方

MCP brief/plan_task/worktree_guard/finish_task/memory_write/mcp_feedback 均返回 Transport closed；release_gate 与测试改用 shell/函数级 fallback。

## 缺少的工具 / 能力

需要可重连 MCP transport 或官方 CLI fallback。

## 升级建议

为项目工具台提供 health/reconnect 指令；finish_task/memory_write/mcp_feedback 提供稳定 CLI 入口。

## 建议移除或合并的工具

无

## 其他备注

release_gate shell 输出完整 RELEASE_GATE_JSON，可作为 MCP job 断连时的证据来源。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 453,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "code_explore",
    "calls": 281,
    "error": 0,
    "avg_duration_seconds": 0.341
  },
  {
    "tool": "worktree_guard",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 169,
    "error": 4,
    "avg_duration_seconds": 0.324
  },
  {
    "tool": "brief",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.765
  },
  {
    "tool": "plan_task",
    "calls": 136,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "code_impact",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "call_capability",
    "calls": 119,
    "error": 5,
    "avg_duration_seconds": 0.297
  },
  {
    "tool": "sql",
    "calls": 116,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "routes",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.051
  }
]
```
