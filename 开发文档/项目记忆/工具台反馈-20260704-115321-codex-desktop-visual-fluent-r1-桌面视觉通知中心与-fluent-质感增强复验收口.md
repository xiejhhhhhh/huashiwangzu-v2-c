---
name: "工具台反馈-20260704-115321-codex-desktop-visual-fluent-r1-桌面视觉通知中心与 Fluent 质感增强复验收口"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-visual-fluent-r1"
created: "2026-07-04T11:53:21.755700+00:00"
---

# MCP 使用反馈

## 任务

桌面视觉通知中心与 Fluent 质感增强复验收口

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 直接给出通知中心与任务栏文件源码，边界守卫能明确区分并行脏改与本次新增 forbidden 命中。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

当前工作区并行任务很多，finish/worktree_guard 需要手动维护较长 baseline_paths，容易遗漏中文项目记忆或其他 agent 反馈文件。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 支持把首次 guard 输出作为 named baseline，或支持 baseline_prefixes，减少大工作区多 agent 并行时的手写列表。

## 升级建议

为项目记忆类文件增加按 agent/tag 自动归类过滤，边界报告中把 allowed project memory 与产品代码分开显示，会更容易读。

## 建议移除或合并的工具

无

## 其他备注

本次没有使用新子代理继续视觉任务，因为收到的两个子代理回报属于另一封 Artifact 执行信；主会话完成了视觉任务验证与收口。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 297,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 181,
    "error": 0,
    "avg_duration_seconds": 0.337
  },
  {
    "tool": "worktree_guard",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 119,
    "error": 3,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "call_capability",
    "calls": 100,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 95,
    "error": 0,
    "avg_duration_seconds": 0.749
  },
  {
    "tool": "plan_task",
    "calls": 93,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 92,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "finish_task",
    "calls": 61,
    "error": 0,
    "avg_duration_seconds": 1.422
  }
]
```
