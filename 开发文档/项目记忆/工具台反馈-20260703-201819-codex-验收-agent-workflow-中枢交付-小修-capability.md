---
name: "工具台反馈-20260703-201819-codex-验收 Agent workflow 中枢交付，小修 capability"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-03T20:18:19.631143+00:00"
---

# MCP 使用反馈

## 任务

验收 Agent workflow 中枢交付，小修 capability 参数漂移，并写入二阶段执行信

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_explore/code_node 能快速定位 workflow_service 和 handler，capability_contract_diff 抓到了真实漂移。

## 本次用到的工具

plan_task, worktree_guard, code_explore, code_node, code_impact, routes, lint, run_test, capability_contract_diff, finish_task, memory_write

## 卡点 / 不顺手的地方

capability_contract_diff 当前似乎只能识别 register_capability 调用附近的字面量参数，抽常量字典后仍判 runtime_keys 为空，只能改成内联字面量。

## 缺少的工具 / 能力

希望 capability_contract_diff 支持解析同文件常量字典引用。

## 升级建议

增强 capability_contract_diff 的 AST 常量追踪，支持 parameters=CONSTANT_DICT['action'] 这类常见写法。

## 建议移除或合并的工具

无

## 其他备注

当前工作区并行改动多，finish_task baseline 能处理但输出很长。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1427,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 675,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "probe",
    "calls": 674,
    "error": 8,
    "avg_duration_seconds": 0.443
  },
  {
    "tool": "code_explore",
    "calls": 661,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 586,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 538,
    "error": 18,
    "avg_duration_seconds": 0.652
  },
  {
    "tool": "worktree_guard",
    "calls": 523,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 487,
    "error": 3,
    "avg_duration_seconds": 4.456
  },
  {
    "tool": "code_impact",
    "calls": 477,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 430,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
