---
name: "工具台反馈-20260704-092511-codex-asset-lifecycle-closure-r1-资产生命周期总收口与测试污染门禁：ContentPackage/Know"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-asset-lifecycle-closure-r1"
created: "2026-07-04T09:25:11.548329+00:00"
---

# MCP 使用反馈

## 任务

资产生命周期总收口与测试污染门禁：ContentPackage/Knowledge/test pollution/release gate 闭环实现与验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/worktree_guard/release_gate/sql/call_capability/run_test 能支撑完整验收。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, sql, call_capability, probe, release_gate, lint, run_test, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task 同时跑 backend/tests 与 repo-root 测试时没有按 backend cwd/env 分组，导致 JWT_SECRET 误报；新加 MCP tool 在当前 server 未重载前无法通过 tool_search 找到，只能用 Python 直接验证。

## 缺少的工具 / 能力

希望有按当前已修改 server.py 动态刷新/重载项目工具台工具列表的能力，或 tool_search 标记“代码已新增但当前 MCP 进程未加载”。

## 升级建议

finish_task 的 test_targets 可复用 run_test 的路径归一化与 cwd 分组逻辑，避免 backend 测试从仓库根被错误收集。

## 建议移除或合并的工具

无

## 其他备注

release_gate 对 clean_release_ready 和三项资产债务的机器 JSON 输出很好用，适合后续作为发布门禁固定检查。

## 当前工具热度快照

```json
[
  {
    "tool": "sql",
    "calls": 14,
    "error": 1,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "call_capability",
    "calls": 12,
    "error": 0,
    "avg_duration_seconds": 0.416
  },
  {
    "tool": "probe",
    "calls": 10,
    "error": 0,
    "avg_duration_seconds": 0.678
  },
  {
    "tool": "run_test",
    "calls": 9,
    "error": 0,
    "avg_duration_seconds": 4.576
  },
  {
    "tool": "code_impact",
    "calls": 5,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "code_node",
    "calls": 5,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "lint",
    "calls": 5,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "finish_task",
    "calls": 4,
    "error": 0,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "worktree_guard",
    "calls": 3,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "release_gate",
    "calls": 2,
    "error": 0,
    "avg_duration_seconds": 2.465
  }
]
```
