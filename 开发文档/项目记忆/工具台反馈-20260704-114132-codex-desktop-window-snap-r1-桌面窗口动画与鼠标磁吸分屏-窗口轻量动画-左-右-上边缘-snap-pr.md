---
name: "工具台反馈-20260704-114132-codex-desktop-window-snap-r1-桌面窗口动画与鼠标磁吸分屏：窗口轻量动画、左/右/上边缘 snap pr"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-window-snap-r1"
created: "2026-07-04T11:41:32.149380+00:00"
---

# MCP 使用反馈

## 任务

桌面窗口动画与鼠标磁吸分屏：窗口轻量动画、左/右/上边缘 snap preview 与落位、顶部最大化恢复、多窗口 zIndex 激活补修、专项 Playwright 覆盖。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/worktree_guard/codegraph/finish_task 串起来能很好控制框架任务边界。

## 本次用到的工具

brief
plan_task
worktree_guard
code_explore
code_node
code_impact
finish_task
memory_write
mcp_feedback

## 卡点 / 不顺手的地方

当前 worktree 多任务并行脏文件很多，worktree_guard 输出很长；需要手工整理 baseline_paths 才能准确表达本轮没有越界。

## 缺少的工具 / 能力

希望 finish_task/worktree_guard 支持直接引用某次 worktree_guard 输出作为基线，减少大段 baseline_paths 手填。

## 升级建议

增加“保存开工基线 id / 收工引用基线 id”的轻量机制，并在输出里单独列本轮新增 allowed 文件。

## 建议移除或合并的工具

无

## 其他备注

子代理复核很有帮助，抓到了 mouseup 重算吸附、关闭动画截断、测试 mock 吞 API 等细节。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 250,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 151,
    "error": 0,
    "avg_duration_seconds": 0.334
  },
  {
    "tool": "probe",
    "calls": 105,
    "error": 3,
    "avg_duration_seconds": 0.349
  },
  {
    "tool": "worktree_guard",
    "calls": 99,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "call_capability",
    "calls": 96,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "sql",
    "calls": 91,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 78,
    "error": 0,
    "avg_duration_seconds": 0.745
  },
  {
    "tool": "plan_task",
    "calls": 75,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 73,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "run_test",
    "calls": 58,
    "error": 0,
    "avg_duration_seconds": 5.004
  }
]
```
