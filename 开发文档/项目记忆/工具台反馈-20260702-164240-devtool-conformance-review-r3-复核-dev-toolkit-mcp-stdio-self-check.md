---
name: "工具台反馈-20260702-164240-devtool-conformance-review-r3-复核 dev_toolkit MCP stdio self-check "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "devtool-conformance-review-r3"
created: "2026-07-02T16:42:40.204866+00:00"
---

# MCP 使用反馈

## 任务

复核 dev_toolkit MCP stdio self-check 修复与 capability conformance gate，跑 dev_toolkit tests/ruff 并报告。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台自检和 CodeGraph 能快速定位；但 run_test/finish_task 在混合 dev_toolkit 与 backend 测试目标时误归一化路径。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, tail_log, lint, run_test, mcp_self_check, dev_toolkit_architecture_audit, finish_task, memory_write

## 卡点 / 不顺手的地方

run_test 将 `backend/tests/test_module_boundary_contracts.py` 在混合目标中归一化成不存在的 `tests/test_module_boundary_contracts.py`；finish_task 继承该问题导致收工 tests 段假失败。

## 缺少的工具 / 能力

无

## 升级建议

修复 run_test/normalize_pytest_targets：当 cwd 为 repo root 且目标包含 backend/tests 与仓库外层 dev_toolkit 测试混跑时，应保留可执行路径或分别选择 cwd。finish_task 可允许传入外部已验证结果，避免重复触发已知归一化坑。

## 建议移除或合并的工具

无

## 其他备注

直接 pytest 验证已通过：dev_toolkit 92 passed；目标 MCP/gate 测试 13 passed。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 369,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 264,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "code_explore",
    "calls": 179,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "sql",
    "calls": 171,
    "error": 7,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 115,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 112,
    "error": 0,
    "avg_duration_seconds": 2.31
  },
  {
    "tool": "db_schema",
    "calls": 107,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 86,
    "error": 0,
    "avg_duration_seconds": 0.566
  },
  {
    "tool": "plan_task",
    "calls": 79,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
