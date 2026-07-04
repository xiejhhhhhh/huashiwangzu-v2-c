---
name: "工具台反馈-20260704-111125-codex-desktop-window-snap-r1-桌面窗口动画与鼠标磁吸分屏：实现窗口轻量动画、鼠标边缘 snap pre"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-window-snap-r1"
created: "2026-07-04T11:11:25.480111+00:00"
---

# MCP 使用反馈

## 任务

桌面窗口动画与鼠标磁吸分屏：实现窗口轻量动画、鼠标边缘 snap preview 与落位，并补 Playwright 验证。

## 顺畅度

- 评分：4/5
- 体感：工具台整体顺畅，CodeGraph 定位和 finish_task 收口很有用。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

并行/外部 worktree 脏改动出现后，worktree_guard 会把非本任务改动一并判入 forbidden；需要人工在最终报告里解释归属。

## 缺少的工具 / 能力

缺少一种“从初始 clean 基线后只标记本会话触碰文件”的辅助视图，方便并行任务下归因。

## 升级建议

worktree_guard/finish_task 可支持传入本会话实际触碰文件清单，单独输出 task-owned boundary 与 whole-worktree boundary 两份结果。

## 建议移除或合并的工具

无

## 其他备注

本任务未修改 backend/dev_toolkit/modules/shared 文件；全量边界失败来自并行/外部脏改动。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 133,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "code_explore",
    "calls": 85,
    "error": 0,
    "avg_duration_seconds": 0.341
  },
  {
    "tool": "call_capability",
    "calls": 80,
    "error": 5,
    "avg_duration_seconds": 0.294
  },
  {
    "tool": "worktree_guard",
    "calls": 65,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "code_impact",
    "calls": 54,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "brief",
    "calls": 50,
    "error": 0,
    "avg_duration_seconds": 0.732
  },
  {
    "tool": "plan_task",
    "calls": 48,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "sql",
    "calls": 45,
    "error": 3,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 43,
    "error": 1,
    "avg_duration_seconds": 0.459
  },
  {
    "tool": "run_test",
    "calls": 39,
    "error": 0,
    "avg_duration_seconds": 4.832
  }
]
```
