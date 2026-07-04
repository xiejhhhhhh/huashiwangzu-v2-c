---
name: "工具台反馈-20260704-111712-codex-backend-semantic-failure-r1-后端语义失败统一与假绿归零：统一 module/task/health/"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-backend-semantic-failure-r1"
created: "2026-07-04T11:17:12.320940+00:00"
---

# MCP 使用反馈

## 任务

后端语义失败统一与假绿归零：统一 module/task/health/dev_toolkit 错误语义，拒绝未知 task_type，补测试与活栈验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/worktree_guard/code_explore/probe/call_capability 很好用，能快速锁定假绿路径。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, routes, capabilities, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 run_test 从仓库根跑后端测试时未加载 backend/.env，导致 JWT_SECRET 空；实际按项目文档 cd backend 或 source backend/.env 后测试通过。工作区并发 dirty 会让 finish_task 边界检查整体失败，需人工区分本轮改动。

## 缺少的工具 / 能力

希望 finish_task 支持传入“本轮实际改动文件清单”与“已知非本轮 dirty 清单”，分开展示 owned/unowned dirty。

## 升级建议

run_test/finish_task 可自动识别 backend/tests 目标并切到 backend cwd 或加载 backend/.env；release_gate blocker 可以在摘要里给出更短的 machine-json 关键字段。

## 建议移除或合并的工具

无

## 其他备注

全量 ruff backend/app dev_toolkit 暴露大量既有 lint 债，本轮改动文件级 ruff 通过；release_gate preflight 因已有 test data pollution active=9 判 BLOCKER，说明门禁未假绿。

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
    "calls": 86,
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
