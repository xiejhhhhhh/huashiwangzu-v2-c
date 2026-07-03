---
name: "工具台反馈-20260703-054354-codex-devtool-queue-selfcheck-worker-收口验证 dev_toolkit/OpenCode MCP 队列文件锁与"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-devtool-queue-selfcheck-worker"
created: "2026-07-03T05:43:54.180779+00:00"
---

# MCP 使用反馈

## 任务

收口验证 dev_toolkit/OpenCode MCP 队列文件锁与 mcp_self_check

## 顺畅度

- 评分：5/5
- 体感：整体顺畅，brief/plan/worktree_guard/codegraph/finish_task 能把验证证据串起来。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

mcp_self_check 的 Python API 返回 JSON 字符串，直接字段访问会 AttributeError；测试已按 json.loads 使用，但交互式验证容易踩一下。

## 缺少的工具 / 能力

无

## 升级建议

可以考虑在 insight_tools 暴露一个 dict 版内部函数，MCP wrapper 再负责 JSON 序列化，方便本地 Python 直接断言。

## 建议移除或合并的工具

无

## 其他备注

未做代码补丁；指定 ruff/pytest/self-check 和并发压力验证均通过。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 490,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 364,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 270,
    "error": 0,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "worktree_guard",
    "calls": 204,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 195,
    "error": 2,
    "avg_duration_seconds": 3.183
  },
  {
    "tool": "code_impact",
    "calls": 169,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 163,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "plan_task",
    "calls": 146,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "brief",
    "calls": 139,
    "error": 0,
    "avg_duration_seconds": 0.802
  }
]
```
