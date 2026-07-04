---
name: "工具台反馈-20260704-114618-codex-desktop-visual-fluent-r1-桌面视觉通知中心与 Fluent 质感增强：分层通知中心、Fluent "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-desktop-visual-fluent-r1"
created: "2026-07-04T11:46:18.408535+00:00"
---

# MCP 使用反馈

## 任务

桌面视觉通知中心与 Fluent 质感增强：分层通知中心、Fluent 质感、键盘可访问性、最小 Playwright 验证。

## 顺畅度

- 评分：5/5
- 体感：顺畅；brief/plan_task/worktree_guard/code_explore/finish_task 对并行 dirty 场景很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 对允许目录里的并行项目记忆和其它 frontend/tests untracked 也会算 new，需要人工解释哪些才是本任务产物。

## 缺少的工具 / 能力

希望 finish_task 能直接接收 forbidden_prefixes，并在最终摘要里区分“本任务显式产物”和“允许路径内并行产物”。

## 升级建议

为前端任务增加 npm build / Playwright / rg 类型压制扫描的结构化验证 wrapper，统一记录命令、耗时和结果。

## 建议移除或合并的工具

无

## 其他备注

本轮还用了两个只读子代理审查视觉实现和测试覆盖，随后主会话补了键盘/Esc 可访问性测试。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 271,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 169,
    "error": 0,
    "avg_duration_seconds": 0.335
  },
  {
    "tool": "worktree_guard",
    "calls": 113,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 109,
    "error": 3,
    "avg_duration_seconds": 0.346
  },
  {
    "tool": "call_capability",
    "calls": 97,
    "error": 5,
    "avg_duration_seconds": 0.292
  },
  {
    "tool": "sql",
    "calls": 95,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 89,
    "error": 0,
    "avg_duration_seconds": 0.747
  },
  {
    "tool": "plan_task",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 82,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "run_test",
    "calls": 59,
    "error": 0,
    "avg_duration_seconds": 4.982
  }
]
```
