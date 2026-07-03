---
name: "工具台反馈-20260703-112048-codex-contract-lane-r4-R4 模块能力契约 drift 第一稳定节点：运行 capability"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-contract-lane-r4"
created: "2026-07-03T11:20:48.165684+00:00"
---

# MCP 使用反馈

## 任务

R4 模块能力契约 drift 第一稳定节点：运行 capability_contract_diff，修复 agent/desktop-tools/image-gen 确定性漂移并复扫至 0 drift。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，capability_contract_diff 对本域定位很准。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, capability_contract_diff, memory_write

## 卡点 / 不顺手的地方

agent/bootstrap 的 tuple 已可解析，但同一处动态 register_capability 仍会被计为 uncheckable，需要代码侧别名规避。

## 缺少的工具 / 能力

无

## 升级建议

建议 contract_tools 在已识别 capabilities tuple 且 loop 仅注册该 tuple 时，不再把对应 register_capability 计为 dynamic uncheckable。

## 建议移除或合并的工具

无

## 其他备注

无

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
    "calls": 614,
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
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
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
