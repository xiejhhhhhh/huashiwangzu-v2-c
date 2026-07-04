---
name: "工具台反馈-20260704-141245-codex-验收并提交全部并行回信到 main，清理工作区并跑 release_ga"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-04T14:12:45.353169+00:00"
---

# MCP 使用反馈

## 任务

验收并提交全部并行回信到 main，清理工作区并跑 release_gate 收工检查

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；release_gate、worktree_guard、probe、run_test/lint 能形成闭环。

## 本次用到的工具

code_explore,routes,probe,worktree_guard,lint,run_test,release_gate,finish_task,memory_write,mcp_feedback,Bash

## 卡点 / 不顺手的地方

release_gate full 可能超时，需要用后台 job；finish_task 输出过长；task debt governance 能分类但无法自动治理 deleted-doc kb_pipeline 失败。

## 缺少的工具 / 能力

希望有一个一键 concise validation report 工具：自动汇总最近 lint/test/build/gate/commit 状态为短表格。

## 升级建议

为 task debt governance 增加 allowlisted deleted-doc/no-file-row kb_pipeline 归档策略，或提供安全的 mark_obsolete action；finish_task 增加 compact=true。

## 建议移除或合并的工具

无

## 其他备注

本次已按用户偏好压缩最终汇报，避免长篇叙述。

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
    "calls": 283,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "worktree_guard",
    "calls": 181,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 175,
    "error": 4,
    "avg_duration_seconds": 0.323
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
    "calls": 98,
    "error": 0,
    "avg_duration_seconds": 0.055
  }
]
```
