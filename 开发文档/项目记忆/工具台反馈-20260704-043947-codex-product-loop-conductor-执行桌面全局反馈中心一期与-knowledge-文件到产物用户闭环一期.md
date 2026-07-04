---
name: "工具台反馈-20260704-043947-codex-product-loop-conductor-执行桌面全局反馈中心一期与 Knowledge 文件到产物用户闭环一期。"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-product-loop-conductor"
created: "2026-07-04T04:39:47.092436+00:00"
---

# MCP 使用反馈

## 任务

执行桌面全局反馈中心一期与 Knowledge 文件到产物用户闭环一期。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/worktree_guard/code_explore/routes/capabilities/probe/call_capability/finish_task 都有效支撑了脏工作区下的边界控制和活栈验证。

## 本次用到的工具

brief, plan_task, worktree_guard, memory_recent, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在超大 dirty 且项目记忆大量未跟踪时输出很长，baseline_paths 手工传入很笨重，容易截断或遗漏。

## 缺少的工具 / 能力

希望有“保存当前 dirty 为 named baseline / finish_task 直接引用 baseline id”的工具；希望有针对本轮 touched files 的 lightweight boundary diff。

## 升级建议

为多代理任务增加 conductor helper：自动记录子代理 id、完成摘要、释放状态，并生成最终交付表；finish_task 可支持从首次 worktree_guard 输出中返回 baseline_id。

## 建议移除或合并的工具

无。

## 其他备注

本次遵守不提交 commit；未修改 backend/app routers、modules/agent、dev_toolkit 禁止文件。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1466,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "probe",
    "calls": 707,
    "error": 8,
    "avg_duration_seconds": 0.436
  },
  {
    "tool": "code_explore",
    "calls": 697,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "lint",
    "calls": 681,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "sql",
    "calls": 590,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 583,
    "error": 18,
    "avg_duration_seconds": 0.623
  },
  {
    "tool": "worktree_guard",
    "calls": 545,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 504,
    "error": 3,
    "avg_duration_seconds": 4.424
  },
  {
    "tool": "code_impact",
    "calls": 493,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 443,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
