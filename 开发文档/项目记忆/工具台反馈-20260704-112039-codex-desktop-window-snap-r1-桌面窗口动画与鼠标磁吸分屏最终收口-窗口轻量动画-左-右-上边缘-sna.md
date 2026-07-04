---
name: "工具台反馈-20260704-112039-codex-desktop-window-snap-r1-桌面窗口动画与鼠标磁吸分屏最终收口：窗口轻量动画、左/右/上边缘 sna"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-window-snap-r1"
created: "2026-07-04T11:20:39.647799+00:00"
---

# MCP 使用反馈

## 任务

桌面窗口动画与鼠标磁吸分屏最终收口：窗口轻量动画、左/右/上边缘 snap preview 与落位、顶部最大化还原尺寸，Playwright 三路径验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；CodeGraph 和 Playwright 组合能很快定位交互点并验证真实拖拽。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

并行 worktree 中出现大量其他任务脏改动，finish_task 的全量边界检查会把非本任务改动一起列为 outside_allowed，需要人工说明归属。

## 缺少的工具 / 能力

缺少任务归属级 dirty 视图；如果能记录本会话 apply_patch/创建文件清单，会更容易在并行工作区判定边界。

## 升级建议

worktree_guard/finish_task 可输出 task-owned files 与 whole-worktree files 两层边界结果；Playwright 失败时可自动摘要当前 URL、主导航、失败前 10 个 API 状态。

## 建议移除或合并的工具

无

## 其他备注

本次最终专项测试覆盖左半屏、右半屏、顶部最大化和顶部恢复原尺寸；测试 catch-all API mock 修正为只匹配 path 以 /api/ 开头，避免误拦截 Vite /src/shared/api/*.ts 模块。

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
    "tool": "call_capability",
    "calls": 88,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "code_explore",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "probe",
    "calls": 73,
    "error": 3,
    "avg_duration_seconds": 0.38
  },
  {
    "tool": "worktree_guard",
    "calls": 70,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "code_impact",
    "calls": 59,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 54,
    "error": 3,
    "avg_duration_seconds": 0.031
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
    "tool": "run_test",
    "calls": 48,
    "error": 0,
    "avg_duration_seconds": 4.916
  }
]
```
