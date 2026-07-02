---
name: "工具台反馈-20260702-165859-release-verification-r4-发布前独立验收验证矩阵：focused backend/dev_tool"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "release-verification-r4"
created: "2026-07-02T16:58:59.433538+00:00"
---

# MCP 使用反馈

## 任务

发布前独立验收验证矩阵：focused backend/dev_toolkit/memory/knowledge/frontend/diff/release_gate。

## 顺畅度

- 评分：3/5
- 体感：主体顺畅，但 release_gate MCP 工具与命令行当前源码出现不一致，需要校准。

## 本次用到的工具

brief, plan_task, worktree_guard, routes, probe, release_gate, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

MCP release_gate(skip_ui=true) 曾报 task queue audit missing summary.failed；同一时间直接命令行 python3.14 dev_toolkit/release_gate.py --skip-ui 可正常解析并 PASS_WITH_DEBT。smoke.py 没有 CLI help/--skip-ui 参数，误用参数会直接跑完整 UI smoke，容易污染队列。

## 缺少的工具 / 能力

建议提供 queue recent failed 明细查询工具，便于发布验收定位新增失败来源；建议 release_gate 工具返回底层命令路径/解释器/源码版本。

## 升级建议

给 smoke.py 增加 argparse，支持 --skip-ui 与 --help；MCP release_gate 改为直接调用当前工作区脚本或暴露 server reload/version，避免工具进程使用旧逻辑；release_gate 可在 audit baseline 失败时附原始 audit payload 摘要。

## 建议移除或合并的工具

无

## 其他备注

本轮未改业务代码。误用 smoke.py 参数造成 3 条 recent failed 验证噪音，已在 memory 中记录。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 389,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 269,
    "error": 0,
    "avg_duration_seconds": 0.016
  },
  {
    "tool": "sql",
    "calls": 198,
    "error": 8,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 193,
    "error": 0,
    "avg_duration_seconds": 0.313
  },
  {
    "tool": "worktree_guard",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 123,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 118,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 2.258
  },
  {
    "tool": "probe",
    "calls": 106,
    "error": 0,
    "avg_duration_seconds": 0.517
  },
  {
    "tool": "plan_task",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
