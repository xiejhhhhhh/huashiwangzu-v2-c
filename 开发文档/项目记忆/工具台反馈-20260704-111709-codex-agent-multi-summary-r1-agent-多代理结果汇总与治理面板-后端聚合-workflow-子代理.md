---
name: "工具台反馈-20260704-111709-codex-agent-multi-summary-r1-Agent 多代理结果汇总与治理面板：后端聚合 workflow 子代理"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-multi-summary-r1"
created: "2026-07-04T11:17:09.926620+00:00"
---

# MCP 使用反馈

## 任务

Agent 多代理结果汇总与治理面板：后端聚合 workflow 子代理/步骤摘要，前端展示摘要面板并支持空状态。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/codegraph/finish_task 对收口帮助明显。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, probe, call_capability, finish_task, memory_write

## 卡点 / 不顺手的地方

lint MCP 对目录 `modules/agent/backend` 报文件不存在，只能对文件列表或用 shell ruff；probe selector 路径不够直观，返回了完整 data 但提示 selector not found。

## 缺少的工具 / 能力

希望有一个专门的活栈测试数据清理工具，按 workflow_run_id 清理 Agent workflow 子表，避免手写 DB 清理脚本。

## 升级建议

finish_task 如果 boundary_check 失败但调用方明确传 risk_note，可在摘要里更突出“本任务允许范围内改动”和“外部 dirty”两组，方便 final 汇报。

## 建议移除或合并的工具

无

## 其他备注

本次使用 3 个子代理：后端 worker、前端 worker、只读 explorer；主会话完成最终集成、重启活栈、验证和清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 138,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "code_explore",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "call_capability",
    "calls": 85,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "worktree_guard",
    "calls": 70,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 65,
    "error": 3,
    "avg_duration_seconds": 0.394
  },
  {
    "tool": "code_impact",
    "calls": 59,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "brief",
    "calls": 52,
    "error": 0,
    "avg_duration_seconds": 0.733
  },
  {
    "tool": "plan_task",
    "calls": 50,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "sql",
    "calls": 49,
    "error": 3,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 48,
    "error": 0,
    "avg_duration_seconds": 4.916
  }
]
```
